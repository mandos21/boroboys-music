"""Browser login, session introspection, and logout endpoints."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated
from urllib.parse import urlencode, urlparse

import httpx
from cryptography.fernet import InvalidToken
from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select

from app.api.deps import DbSession, get_current_session, get_current_user, require_csrf
from app.api.schemas import SessionResponse
from app.auth.oidc import OidcClient, OidcError
from app.core.config import Settings, get_settings
from app.core.security import decrypt, encrypt, hash_secret, new_secret, secrets_match
from app.db.models import OidcLoginAttempt, PlatformRole, ServerSession, User

router = APIRouter(prefix="/auth", tags=["auth"])

# Serializes the one-time empty-database admin bootstrap across API instances.
_INITIAL_ADMIN_LOCK_ID = 4_061_173_091


@router.get("/login")
def login(
    db: DbSession,
    return_path: Annotated[str, Query(alias="return")] = "/",
) -> RedirectResponse:
    settings = get_settings()
    if not settings.oidc_is_configured:
        return _login_error_redirect(settings, "oidc-unavailable")
    if not _is_safe_return_path(return_path):
        return _login_error_redirect(settings, "invalid-request")

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
        redirect_url = OidcClient(settings).authorization_url(state, nonce, code_verifier)
    except (httpx.HTTPError, OidcError):
        db.delete(attempt)
        db.commit()
        return _login_error_redirect(settings, "oidc-unavailable")
    return RedirectResponse(redirect_url, status_code=status.HTTP_303_SEE_OTHER)


@router.get("/callback")
def callback(
    db: DbSession,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    settings = get_settings()
    if error:
        return _login_error_redirect(settings, "denied")
    if not code or not state:
        return _login_error_redirect(settings, "invalid-request")

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
        return _login_error_redirect(settings, "expired-request")
    attempt.consumed_at = datetime.now(UTC)
    db.commit()

    try:
        nonce = decrypt(
            attempt.nonce_ciphertext, settings.credential_encryption_key.get_secret_value()
        )
        if not secrets_match(nonce, attempt.nonce_hash):
            raise OidcError("OIDC nonce storage validation failed")
        identity = OidcClient(settings).complete_login(
            code,
            decrypt(
                attempt.code_verifier_ciphertext,
                settings.credential_encryption_key.get_secret_value(),
            ),
            nonce,
        )
    except (httpx.HTTPError, OidcError, InvalidToken):
        return _login_error_redirect(settings, "verification-failed")

    if settings.oidc_require_verified_email and not identity.email_verified:
        return _login_error_redirect(settings, "email-verification-required")
    # The advisory transaction lock prevents two simultaneous first logins from
    # both observing an empty users table and receiving administrator access.
    db.execute(select(func.pg_advisory_xact_lock(_INITIAL_ADMIN_LOCK_ID)))
    user = db.scalar(
        select(User).where(
            User.oidc_issuer == identity.issuer, User.oidc_subject == identity.subject
        )
    )
    if user is None:
        if not settings.oidc_auto_provision_users:
            return _login_error_redirect(settings, "provisioning-disabled")
        existing_user = db.scalar(select(User.id).limit(1)) is not None
        user = User(
            oidc_issuer=identity.issuer,
            oidc_subject=identity.subject,
            email=identity.email,
            display_name=identity.display_name,
            platform_role=_provisioned_platform_role(
                settings, identity.subject, identity.claims, existing_user
            ),
        )
        db.add(user)
        db.flush()
    elif not user.is_active:
        return _login_error_redirect(settings, "account-inactive")
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


@router.get("/session", response_model=SessionResponse)
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
        "csrfCookieName": _csrf_cookie_name(),
    }


@router.post("/logout", dependencies=[Depends(require_csrf)])
def logout(
    db: DbSession,
    session: Annotated[ServerSession, Depends(get_current_session)],
) -> Response:
    settings = get_settings()
    # End the local session before anything that could fail. The stored ID
    # token is only a hint for the provider's logout page; a session created
    # before a credential-key rotation cannot be decrypted any more, and that
    # must not leave someone signed in.
    id_token = None
    if session.oidc_id_token_ciphertext:
        try:
            id_token = decrypt(
                session.oidc_id_token_ciphertext,
                settings.credential_encryption_key.get_secret_value(),
            )
        except InvalidToken:
            id_token = None
    db.delete(session)
    db.commit()
    try:
        destination = OidcClient(settings).logout_url(id_token)
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


def _login_error_redirect(settings: Settings, reason: str) -> RedirectResponse:
    """Keep browser-facing OIDC failures in the application UI, not raw API JSON."""
    return RedirectResponse(
        f"{str(settings.app_base_url).rstrip('/')}/auth/error?{urlencode({'reason': reason})}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


def _is_safe_return_path(value: str) -> bool:
    parsed = urlparse(value)
    return (
        value.startswith("/")
        and not value.startswith("//")
        and not parsed.scheme
        and not parsed.netloc
    )


def _is_claim_admin(settings: Settings, claims: dict[str, object]) -> bool:
    if not settings.oidc_admin_claim:
        return False
    value = claims.get(settings.oidc_admin_claim)
    values = value if isinstance(value, list) else [value]
    return bool(settings.oidc_admin_claim_values.intersection(str(item) for item in values))


def _provisioned_platform_role(
    settings: Settings,
    subject: str,
    claims: dict[str, object],
    existing_user: bool,
) -> PlatformRole:
    """Determine a local role only when an OIDC identity is first provisioned."""
    if (
        (settings.oidc_bootstrap_first_user_admin and not existing_user)
        or _is_claim_admin(settings, claims)
        or subject in settings.bootstrap_admin_subjects
    ):
        return PlatformRole.ADMIN
    return PlatformRole.MEMBER
