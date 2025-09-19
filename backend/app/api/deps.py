from __future__ import annotations

from typing import Generator, Optional

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from pydantic import ValidationError

from app.config import get_settings
from app.db import models
from app.db.session import get_session_factory
from app.services.lastfm_service import LastFMService
from app.services.playlist_manager import PlaylistManager
from app.services.spotify_service import SpotifyService


class SetupRequired(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            detail="Application setup required.",
            headers={"Location": "/api/v1/setup/status"},
        )


def get_db() -> Generator[Session, None, None]:
    try:
        session_factory = get_session_factory()
    except (ValidationError, ValueError):
        raise SetupRequired

    session = session_factory()
    try:
        yield session
    finally:
        session.close()


def get_current_user(request: Request, db: Session = Depends(get_db)) -> Optional[models.User]:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return db.get(models.User, user_id)


def require_user(user: Optional[models.User] = Depends(get_current_user)) -> models.User:
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return user


def require_admin(user: models.User = Depends(require_user)) -> models.User:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user


def get_spotify_service(request: Request) -> SpotifyService:
    access_token = request.session.get("spotify_access_token")
    if access_token:
        return SpotifyService.from_user_token(access_token)
    return SpotifyService.from_app_credentials()


def get_playlist_manager(
    spotify: SpotifyService = Depends(get_spotify_service),
) -> PlaylistManager:
    settings = get_settings()
    lastfm_service: Optional[LastFMService] = None
    if settings.lastfm_api_key and settings.lastfm_shared_secret:
        try:
            lastfm_service = LastFMService.from_settings()
        except Exception:  # pragma: no cover - defensive
            lastfm_service = None
    return PlaylistManager(spotify_service=spotify, lastfm_service=lastfm_service)
