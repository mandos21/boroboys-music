"""Spotify OAuth and playlist API adapter; no browser-accessible credentials."""

from __future__ import annotations

import base64
import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx

from app.core.config import Settings

SPOTIFY_ACCOUNTS = "https://accounts.spotify.com"
SPOTIFY_API = "https://api.spotify.com/v1"
SCOPES = "playlist-modify-private playlist-modify-public user-read-private"


class SpotifyError(Exception):
    pass


def authorization_url(settings: Settings, state: str, verifier: str) -> str:
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )
    return f"{SPOTIFY_ACCOUNTS}/authorize?{urlencode({'response_type': 'code', 'client_id': settings.spotify_client_id, 'redirect_uri': str(settings.spotify_redirect_uri), 'scope': SCOPES, 'state': state, 'code_challenge_method': 'S256', 'code_challenge': challenge})}"


def exchange_code(settings: Settings, code: str, verifier: str) -> dict[str, Any]:
    if not settings.spotify_client_id or not settings.spotify_client_secret:
        raise SpotifyError("Spotify is not configured")
    response = httpx.post(
        f"{SPOTIFY_ACCOUNTS}/api/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": str(settings.spotify_redirect_uri),
            "code_verifier": verifier,
        },
        auth=(settings.spotify_client_id, settings.spotify_client_secret.get_secret_value()),
        timeout=15.0,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict) or not isinstance(payload.get("access_token"), str):
        raise SpotifyError("Spotify returned no access token")
    return payload


def current_profile(access_token: str) -> dict[str, Any]:
    response = httpx.get(f"{SPOTIFY_API}/me", headers=_headers(access_token), timeout=15.0)
    response.raise_for_status()
    profile = response.json()
    if not isinstance(profile, dict) or not isinstance(profile.get("id"), str):
        raise SpotifyError("Spotify returned no profile identity")
    return profile


def create_playlist(access_token: str, user_id: str, name: str, description: str) -> str:
    response = httpx.post(
        f"{SPOTIFY_API}/users/{user_id}/playlists",
        headers=_headers(access_token),
        json={"name": name, "description": description, "public": False},
        timeout=15.0,
    )
    response.raise_for_status()
    playlist = response.json()
    if not isinstance(playlist, dict) or not isinstance(playlist.get("id"), str):
        raise SpotifyError("Spotify returned no playlist ID")
    return str(playlist["id"])


def add_items(access_token: str, playlist_id: str, uris: list[str]) -> None:
    for start in range(0, len(uris), 100):
        response = httpx.post(
            f"{SPOTIFY_API}/playlists/{playlist_id}/items",
            headers=_headers(access_token),
            json={"uris": uris[start : start + 100]},
            timeout=15.0,
        )
        response.raise_for_status()


def retire_playlist(access_token: str, playlist_id: str, uris: list[str]) -> None:
    for start in range(0, len(uris), 100):
        response = httpx.request(
            "DELETE",
            f"{SPOTIFY_API}/playlists/{playlist_id}/items",
            headers=_headers(access_token),
            json={"tracks": [{"uri": uri} for uri in uris[start : start + 100]]},
            timeout=15.0,
        )
        response.raise_for_status()
    response = httpx.put(
        f"{SPOTIFY_API}/playlists/{playlist_id}",
        headers=_headers(access_token),
        json={"public": False},
        timeout=15.0,
    )
    response.raise_for_status()


def token_expiry(payload: dict[str, Any]) -> datetime | None:
    seconds = payload.get("expires_in")
    return datetime.now(UTC) + timedelta(seconds=seconds) if isinstance(seconds, int) else None


def _headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
