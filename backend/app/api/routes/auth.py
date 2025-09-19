from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse, RedirectResponse
from loguru import logger
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.auth.spotify_auth import create_spotify_oauth
from app.bootstrap import initialize_database
from app.config import get_settings
from app.db import crud
from app.api.deps import get_db
from app.core.state import generate_signed_state, validate_signed_state
from app.services.spotify_service import SpotifyService
from app.services import setup_service

router = APIRouter()


@router.get("/auth/login")
def request_login(request: Request, redirect_to: Optional[str] = None, invite: Optional[str] = None) -> JSONResponse:
    if not setup_service.settings_ready():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Setup incomplete")

    settings = get_settings()
    state = generate_signed_state(settings.secret_key)
    request.session["oauth_state"] = state
    if redirect_to:
        request.session["post_login_redirect"] = redirect_to
    if invite:
        request.session["invite_token"] = invite

    oauth = create_spotify_oauth(state=state)
    auth_url = oauth.get_authorize_url()
    return JSONResponse({"authorization_url": auth_url, "state": state})


@router.get("/auth/callback")
def complete_login(request: Request, db: Session = Depends(get_db)) -> Response:
    if not setup_service.settings_ready():
        return RedirectResponse(url="/api/v1/setup/status", status_code=status.HTTP_307_TEMPORARY_REDIRECT)

    params = request.query_params
    code = params.get("code")
    state = params.get("state")
    invite_token = params.get("invite")

    if not code:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing authorization code")

    settings = get_settings()
    expected_state = request.session.get("oauth_state")
    if not validate_signed_state(state, settings.secret_key):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid state parameter")
    if expected_state and expected_state != state:
        logger.debug("State mismatch but signature valid; continuing.")

    try:
        initialize_database(settings.database_url)
    except SQLAlchemyError as exc:
        logger.error("Database initialization failed: {}", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database initialization failed")

    oauth = create_spotify_oauth(state=state)
    try:
        token_info = oauth.get_access_token(code, as_dict=True)
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Spotify OAuth failed: {}", exc)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Spotify authentication failed")

    if not token_info:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No token returned from Spotify")

    access_token = token_info["access_token"]
    refresh_token = token_info.get("refresh_token")
    expires_at = datetime.fromtimestamp(token_info["expires_at"], tz=timezone.utc)
    scope = token_info.get("scope", oauth.scope or "")

    spotify_service = SpotifyService.from_user_token(access_token)
    profile = spotify_service.current_user()
    spotify_user_id = profile["id"]
    display_name = profile.get("display_name") or spotify_user_id
    email = profile.get("email")
    images = profile.get("images") or []
    avatar_url = None
    for image in images:
        url = image.get("url")
        if url:
            avatar_url = url
            break

    invite_value = invite_token or request.session.get("invite_token")
    try:
        user = crud.upsert_spotify_user(
            db,
            spotify_user_id=spotify_user_id,
            username=spotify_user_id,
            display_name=display_name,
            email=email,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
            scope=scope,
            invite_token=invite_value,
            avatar_url=avatar_url,
        )
    except PermissionError as exc:
        logger.warning("Spotify user login blocked: {}", exc)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))

    db.commit()
    db.refresh(user)

    request.session["user_id"] = user.id
    request.session["spotify_access_token"] = access_token
    request.session["oauth_state"] = generate_signed_state(settings.secret_key)
    request.session.pop("invite_token", None)

    redirect_target = (
        request.session.pop("post_login_redirect", None)
        or settings.frontend_redirect_url
        or "/"
    )

    response = RedirectResponse(url=redirect_target, status_code=status.HTTP_302_FOUND)
    return response


@router.post("/auth/logout")
def logout(request: Request) -> JSONResponse:
    request.session.clear()
    return JSONResponse({"status": "logged_out"})
