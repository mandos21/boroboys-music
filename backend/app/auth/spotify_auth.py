from __future__ import annotations

from typing import Optional

from spotipy.oauth2 import SpotifyOAuth

from app.config import get_settings


def create_spotify_oauth(state: Optional[str] = None) -> SpotifyOAuth:
    settings = get_settings()
    missing = [
        name
        for name, value in (
            ("SPOTIFY_CLIENT_ID", settings.spotify_client_id),
            ("SPOTIFY_CLIENT_SECRET", settings.spotify_client_secret),
            ("SPOTIFY_REDIRECT_URI", settings.spotify_redirect_uri),
        )
        if not value
    ]
    if missing:
        missing_csv = ", ".join(missing)
        raise ValueError(
            f"Missing Spotify configuration: {missing_csv}. Update your environment settings and reload."
        )
    return SpotifyOAuth(
        client_id=settings.spotify_client_id,
        client_secret=settings.spotify_client_secret,
        redirect_uri=settings.spotify_redirect_uri,
        scope=settings.spotify_scope,
        cache_path=None,
        state=state,
    )


def refresh_access_token(refresh_token: str) -> dict:
    oauth = create_spotify_oauth()
    return oauth.refresh_access_token(refresh_token)
