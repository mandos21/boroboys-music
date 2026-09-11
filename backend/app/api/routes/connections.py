"""User-managed external account links and listening-evidence visibility."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import DbSession, get_current_user, require_csrf
from app.api.schemas import ConnectionResponse
from app.core.config import Settings, get_settings
from app.core.security import decrypt, encrypt, hash_secret, new_secret
from app.db.models import (
    EvidenceVisibility,
    ExternalAccount,
    ExternalCredential,
    ExternalLinkAttempt,
    ExternalProvider,
    User,
)
from app.services import lastfm, spotify

router = APIRouter(prefix="/connections", tags=["connections"])


class VisibilityUpdate(BaseModel):
    visibility: EvidenceVisibility


@router.get("", response_model=list[ConnectionResponse])
def list_connections(
    db: DbSession, user: Annotated[User, Depends(get_current_user)]
) -> list[dict[str, object]]:
    accounts = list(
        db.scalars(
            select(ExternalAccount)
            .where(ExternalAccount.user_id == user.id)
            .order_by(ExternalAccount.provider, ExternalAccount.created_at)
        )
    )
    return [
        {
            "id": str(account.id),
            "provider": account.provider.value,
            "displayName": account.display_name,
            "profileImageUrl": account.profile_image_url,
            "visibility": account.evidence_visibility.value,
            "isActive": account.is_active,
            "disconnectedAt": account.disconnected_at.isoformat()
            if account.disconnected_at
            else None,
        }
        for account in accounts
    ]


@router.get("/spotify/login")
def begin_spotify_link(
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> RedirectResponse:
    settings = get_settings()
    if not settings.spotify_is_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Spotify is not configured"
        )
    state, verifier = new_secret(), new_secret()
    attempt = ExternalLinkAttempt(
        user_id=user.id,
        provider=ExternalProvider.SPOTIFY,
        state_hash=hash_secret(state),
        code_verifier_ciphertext=encrypt(
            verifier, settings.credential_encryption_key.get_secret_value()
        ),
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
    )
    db.add(attempt)
    db.commit()
    return RedirectResponse(spotify.authorization_url(settings, state, verifier), status_code=303)


@router.get("/spotify/callback")
def complete_spotify_link(
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    settings = get_settings()
    if error or not code or not state:
        return _link_result_redirect(settings, "spotify", "denied")
    attempt = _claim_link_attempt(db, ExternalProvider.SPOTIFY, state, user)
    if attempt is None:
        return _link_result_redirect(settings, "spotify", "expired")
    try:
        token = spotify.exchange_code(
            settings,
            code,
            decrypt(
                attempt.code_verifier_ciphertext,
                settings.credential_encryption_key.get_secret_value(),
            ),
        )
        profile = spotify.current_profile(str(token["access_token"]))
    except (httpx.HTTPError, spotify.SpotifyError):
        return _link_result_redirect(settings, "spotify", "failed")
    account = db.scalar(
        select(ExternalAccount).where(
            ExternalAccount.provider == ExternalProvider.SPOTIFY,
            ExternalAccount.provider_subject == profile["id"],
        )
    )
    if account is not None and account.user_id != attempt.user_id:
        return _link_result_redirect(settings, "spotify", "already-linked")
    if account is None:
        account = ExternalAccount(
            user_id=attempt.user_id,
            provider=ExternalProvider.SPOTIFY,
            provider_subject=profile["id"],
            display_name=profile.get("display_name")
            if isinstance(profile.get("display_name"), str)
            else profile["id"],
            profile_image_url=_spotify_profile_image(profile),
            scopes=str(token.get("scope", "")).split(),
        )
        db.add(account)
        db.flush()
    else:
        account.is_active = True
        account.disconnected_at = None
        account.display_name = (
            profile.get("display_name")
            if isinstance(profile.get("display_name"), str)
            else profile["id"]
        )
        account.profile_image_url = _spotify_profile_image(profile)
        # Re-linking is how a listener grants a newly required scope, so the
        # recorded grant has to follow the authorization that just happened.
        account.scopes = str(token.get("scope", "")).split()
    credential = db.scalar(
        select(ExternalCredential).where(ExternalCredential.external_account_id == account.id)
    )
    ciphertext = encrypt(json.dumps(token), settings.credential_encryption_key.get_secret_value())
    if credential is None:
        db.add(
            ExternalCredential(
                external_account_id=account.id,
                ciphertext=ciphertext,
                key_version=settings.credential_encryption_key_version,
                expires_at=spotify.token_expiry(token),
            )
        )
    else:
        credential.ciphertext, credential.expires_at = ciphertext, spotify.token_expiry(token)
    db.commit()
    return _link_result_redirect(settings)


def _claim_link_attempt(
    db: DbSession, provider: ExternalProvider, state: str, user: User
) -> ExternalLinkAttempt | None:
    """Consume the one-time link state, but only for the person who started it.

    The provider redirects the browser back here without any proof of who is
    sitting at it. Without tying the callback to the session that began the
    attempt, an attacker could start a link on their own account, hand the
    resulting authorization URL to someone else, and end up holding that
    person's provider credentials.
    """
    attempt = db.scalar(
        select(ExternalLinkAttempt)
        .where(
            ExternalLinkAttempt.state_hash == hash_secret(state),
            ExternalLinkAttempt.provider == provider,
            ExternalLinkAttempt.expires_at > datetime.now(UTC),
            ExternalLinkAttempt.consumed_at.is_(None),
        )
        .with_for_update()
    )
    if attempt is None or attempt.user_id != user.id:
        return None
    attempt.consumed_at = datetime.now(UTC)
    # Release the row lock before the provider exchange, as the OIDC callback
    # does: a replayed callback should be refused immediately, not queue up
    # behind remote I/O.
    db.commit()
    return attempt


def _link_result_redirect(
    settings: Settings, provider: str | None = None, reason: str | None = None
) -> RedirectResponse:
    """Return a browser to the profile page instead of a raw API error body.

    These endpoints are provider redirects, so the person following them is
    looking at a browser tab, not reading a JSON response.
    """
    query = (
        f"?{urlencode({'linkError': reason, 'provider': provider})}" if provider and reason else ""
    )
    return RedirectResponse(
        f"{str(settings.app_base_url).rstrip('/')}/profile{query}", status_code=303
    )


def _spotify_profile_image(profile: dict[str, object]) -> str | None:
    images = profile.get("images")
    if not isinstance(images, list):
        return None
    for image in images:
        if isinstance(image, dict):
            url = image.get("url")
            if isinstance(url, str):
                return url
    return None


@router.get("/lastfm/login")
def begin_lastfm_link(
    db: DbSession, user: Annotated[User, Depends(get_current_user)]
) -> RedirectResponse:
    settings = get_settings()
    if not settings.lastfm_is_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Last.fm is not configured"
        )
    state = new_secret()
    db.add(
        ExternalLinkAttempt(
            user_id=user.id,
            provider=ExternalProvider.LASTFM,
            state_hash=hash_secret(state),
            code_verifier_ciphertext=encrypt(
                state, settings.credential_encryption_key.get_secret_value()
            ),
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
        )
    )
    db.commit()
    return RedirectResponse(lastfm.authorization_url(settings, state), status_code=303)


@router.get("/lastfm/callback")
def complete_lastfm_link(
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
    token: str | None = None,
    state: str | None = None,
) -> RedirectResponse:
    settings = get_settings()
    if not token or not state:
        return _link_result_redirect(settings, "lastfm", "denied")
    attempt = _claim_link_attempt(db, ExternalProvider.LASTFM, state, user)
    if attempt is None:
        return _link_result_redirect(settings, "lastfm", "expired")
    try:
        session = lastfm.exchange_session(settings, token)
    except (httpx.HTTPError, lastfm.LastfmError):
        return _link_result_redirect(settings, "lastfm", "failed")
    account = db.scalar(
        select(ExternalAccount).where(
            ExternalAccount.provider == ExternalProvider.LASTFM,
            ExternalAccount.provider_subject == session["username"],
        )
    )
    if account is not None and account.user_id != attempt.user_id:
        return _link_result_redirect(settings, "lastfm", "already-linked")
    if account is None:
        account = ExternalAccount(
            user_id=attempt.user_id,
            provider=ExternalProvider.LASTFM,
            provider_subject=session["username"],
            display_name=session["username"],
        )
        db.add(account)
        db.flush()
    else:
        account.is_active = True
        account.disconnected_at = None
        account.display_name = session["username"]
    credential = db.scalar(
        select(ExternalCredential).where(ExternalCredential.external_account_id == account.id)
    )
    ciphertext = encrypt(json.dumps(session), settings.credential_encryption_key.get_secret_value())
    if credential is None:
        db.add(
            ExternalCredential(
                external_account_id=account.id,
                ciphertext=ciphertext,
                key_version=settings.credential_encryption_key_version,
            )
        )
    else:
        credential.ciphertext = ciphertext
    db.commit()
    return _link_result_redirect(settings)


@router.patch("/{account_id}/visibility", dependencies=[Depends(require_csrf)])
def update_visibility(
    account_id: uuid.UUID,
    payload: VisibilityUpdate,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, str]:
    account = db.get(ExternalAccount, account_id)
    if account is None or account.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="linked account not found"
        )
    account.evidence_visibility = payload.visibility
    db.commit()
    return {"id": str(account.id), "visibility": account.evidence_visibility.value}


@router.delete(
    "/{account_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
    dependencies=[Depends(require_csrf)],
)
def disconnect_account(
    account_id: uuid.UUID,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> None:
    account = db.get(ExternalAccount, account_id)
    if account is None or account.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="linked account not found"
        )
    credential = db.scalar(
        select(ExternalCredential).where(ExternalCredential.external_account_id == account.id)
    )
    if credential is not None:
        db.delete(credential)
    account.is_active = False
    account.disconnected_at = datetime.now(UTC)
    db.commit()
