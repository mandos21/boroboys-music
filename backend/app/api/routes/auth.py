"""Browser login, session introspection, and logout endpoints."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from app.api.deps import DbSession, get_current_session, get_current_user, require_csrf
from app.auth.oidc import OidcClient, OidcError
from app.core.config import get_settings
from app.core.security import decrypt, encrypt, hash_secret, new_secret, secrets_match
from app.db.models import OidcLoginAttempt, PlatformRole, ServerSession, User

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/login")
async def login(
    db: DbSession,
    return_path: Annotated[str, Query(alias="return")] = "/",
) -> RedirectResponse:
    settings = get_settings()
    if not settings.oidc_is_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="OIDC is not configured"
        )
    if not _is_safe_return_path(return_path):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid return path"
        )

    state, nonce, code_verifier = new_secret(), new_secret(), new_secret()
    attempt = OidcLoginAttempt(
        state_hash=hash_secret(state),
        nonce_hash=hash_secret(nonce),
        nonce_ciphertext=encrypt(nonce, settings.credential_encryption_key.get_secret_value()),
        code_verifier_ciphertext=encrypt(
            code_verifier, settings.credential_encryption_key.get_secret_value()
        ),
        return_path=return_path,
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
    )
    db.add(attempt)
    db.commit()
    try:
        redirect_url = await OidcClient(settings).authorization_url(state, nonce, code_verifier)
    except (httpx.HTTPError, OidcError) as error:
        db.delete(attempt)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="OIDC unavailable"
        ) from error
    return RedirectResponse(redirect_url, status_code=status.HTTP_303_SEE_OTHER)


@router.get("/callback")
async def callback(
    db: DbSession,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    settings = get_settings()
    if error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="OIDC login was denied"
        )
    if not code or not state:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="missing OIDC callback data"
        )

    attempt = db.scalar(
        select(OidcLoginAttempt)
        .where(
            OidcLoginAttempt.state_hash == hash_secret(state),
            OidcLoginAttempt.expires_at > datetime.now(UTC),
            OidcLoginAttempt.consumed_at.is_(None),
        )
        .with_for_update()
    )
    if attempt is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid or expired OIDC state"
        )
    attempt.consumed_at = datetime.now(UTC)
    db.commit()

    try:
        nonce = decrypt(
            attempt.nonce_ciphertext, settings.credential_encryption_key.get_secret_value()
        )
        if not secrets_match(nonce, attempt.nonce_hash):
            raise OidcError("OIDC nonce storage validation failed")
        identity = await OidcClient(settings).complete_login(
            code,
            decrypt(
                attempt.code_verifier_ciphertext,
                settings.credential_encryption_key.get_secret_value(),
            ),
            nonce,
        )
    except (httpx.HTTPError, OidcError) as exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="OIDC callback validation failed"
        ) from exception

    if settings.oidc_require_verified_email and not identity.email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="a verified email is required"
        )
    user = db.scalar(
        select(User).where(
            User.oidc_issuer == identity.issuer, User.oidc_subject == identity.subject
        )
    )
    if user is None:
        if not settings.oidc_auto_provision_users:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="account provisioning is disabled"
            )
        user = User(
            oidc_issuer=identity.issuer,
            oidc_subject=identity.subject,
            email=identity.email,
            display_name=identity.display_name,
            platform_role=(
                PlatformRole.ADMIN
                if identity.subject in settings.bootstrap_admin_subjects
                else PlatformRole.MEMBER
            ),
        )
        db.add(user)
        db.flush()
    elif not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="account is inactive")
    else:
        user.email = identity.email
        user.display_name = identity.display_name

    session_token, csrf_token = new_secret(), new_secret()
    session = ServerSession(
        user_id=user.id,
        token_hash=hash_secret(session_token),
        csrf_secret_hash=hash_secret(csrf_token),
        oidc_session_id=identity.session_id,
        oidc_id_token_ciphertext=encrypt(
            identity.id_token, settings.credential_encryption_key.get_secret_value()
        ),
        expires_at=datetime.now(UTC) + timedelta(hours=settings.session_lifetime_hours),
    )
    db.add(session)
    db.commit()

    destination = f"{str(settings.app_base_url).rstrip('/')}{attempt.return_path}"
    redirect = RedirectResponse(destination, status_code=status.HTTP_303_SEE_OTHER)
    _set_session_cookies(redirect, session_token, csrf_token)
    return redirect


@router.get("/session")
def session_details(
    session: Annotated[ServerSession, Depends(get_current_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, object]:
    return {
        "user": {
            "id": str(user.id),
            "email": user.email,
            "displayName": user.display_name,
            "platformRole": user.platform_role.value,
        },
        "expiresAt": session.expires_at.isoformat(),
    }


@router.post("/logout", dependencies=[Depends(require_csrf)])
async def logout(
    db: DbSession,
    session: Annotated[ServerSession, Depends(get_current_session)],
) -> Response:
    settings = get_settings()
    id_token = (
        decrypt(
            session.oidc_id_token_ciphertext, settings.credential_encryption_key.get_secret_value()
        )
        if session.oidc_id_token_ciphertext
        else None
    )
    db.delete(session)
    db.commit()
    try:
        destination = await OidcClient(settings).logout_url(id_token)
    except (httpx.HTTPError, OidcError):
        destination = str(settings.oidc_post_logout_redirect_url or settings.app_base_url)
    response = Response(
        status_code=status.HTTP_204_NO_CONTENT, headers={"X-Logout-Redirect": destination}
    )
    response.delete_cookie(settings.session_cookie_name, path="/")
    response.delete_cookie(_csrf_cookie_name(), path="/")
    return response


def _set_session_cookies(response: Response, session_token: str, csrf_token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=settings.session_cookie_name,
        value=session_token,
        max_age=settings.session_lifetime_hours * 60 * 60,
        httponly=True,
        secure=settings.app_env == "production",
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        key=_csrf_cookie_name(),
        value=csrf_token,
        max_age=settings.session_lifetime_hours * 60 * 60,
        httponly=False,
        secure=settings.app_env == "production",
        samesite="lax",
        path="/",
    )


def _csrf_cookie_name() -> str:
    return f"{get_settings().session_cookie_name}_csrf"


def _is_safe_return_path(value: str) -> bool:
    parsed = urlparse(value)
    return (
        value.startswith("/")
        and not value.startswith("//")
        and not parsed.scheme
        and not parsed.netloc
    )
