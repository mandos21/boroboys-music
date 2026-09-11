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
SCOPES = "playlist-modify-private playlist-modify-public playlist-read-private user-read-private"


class SpotifyError(Exception):
    pass


def authorization_url(settings: Settings, state: str, verifier: str) -> str:
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )
    query = urlencode(
        {
            "response_type": "code",
            "client_id": settings.spotify_client_id,
            "redirect_uri": str(settings.spotify_redirect_uri),
            "scope": SCOPES,
            "state": state,
            "code_challenge_method": "S256",
            "code_challenge": challenge,
        }
    )
    return f"{SPOTIFY_ACCOUNTS}/authorize?{query}"


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


def refresh_token(settings: Settings, refresh_token_value: str) -> dict[str, Any]:
    if not settings.spotify_client_id or not settings.spotify_client_secret:
        raise SpotifyError("Spotify is not configured")
    response = httpx.post(
        f"{SPOTIFY_ACCOUNTS}/api/token",
        data={"grant_type": "refresh_token", "refresh_token": refresh_token_value},
        auth=(settings.spotify_client_id, settings.spotify_client_secret.get_secret_value()),
        timeout=15.0,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict) or not isinstance(payload.get("access_token"), str):
        raise SpotifyError("Spotify returned no refreshed access token")
    return payload


def client_credentials_token(settings: Settings) -> str:
    """Obtain an application token for non-user-specific Spotify metadata."""
    if not settings.spotify_client_id or not settings.spotify_client_secret:
        raise SpotifyError("Spotify is not configured")
    response = httpx.post(
        f"{SPOTIFY_ACCOUNTS}/api/token",
        data={"grant_type": "client_credentials"},
        auth=(settings.spotify_client_id, settings.spotify_client_secret.get_secret_value()),
        timeout=15.0,
    )
    response.raise_for_status()
    payload = response.json()
    token = payload.get("access_token") if isinstance(payload, dict) else None
    if not isinstance(token, str):
        raise SpotifyError("Spotify returned no application access token")
    return token


def current_profile(access_token: str) -> dict[str, Any]:
    response = httpx.get(f"{SPOTIFY_API}/me", headers=_headers(access_token), timeout=15.0)
    response.raise_for_status()
    profile = response.json()
    if not isinstance(profile, dict) or not isinstance(profile.get("id"), str):
        raise SpotifyError("Spotify returned no profile identity")
    return profile


def search_tracks(access_token: str, query: str) -> list[dict[str, Any]]:
    response = httpx.get(
        f"{SPOTIFY_API}/search",
        headers=_headers(access_token),
        params={"q": query, "type": "track", "limit": 20},
        timeout=15.0,
    )
    response.raise_for_status()
    payload = response.json()
    tracks = payload.get("tracks", {}).get("items", []) if isinstance(payload, dict) else []
    return [item for item in tracks if isinstance(item, dict)]


def tracks_by_id(access_token: str, track_ids: list[str]) -> list[dict[str, Any]]:
    """Retrieve current Spotify metadata for up to 50 stable track IDs."""
    if not track_ids:
        return []
    response = httpx.get(
        f"{SPOTIFY_API}/tracks",
        headers=_headers(access_token),
        params={"ids": ",".join(track_ids)},
        timeout=15.0,
    )
    response.raise_for_status()
    payload = response.json()
    items = payload.get("tracks", []) if isinstance(payload, dict) else []
    return [item for item in items if isinstance(item, dict)]


def artists_by_id(access_token: str, artist_ids: list[str]) -> list[dict[str, Any]]:
    """Retrieve Spotify artist metadata used for optional profile genre signals."""
    if not artist_ids:
        return []
    response = httpx.get(
        f"{SPOTIFY_API}/artists",
        headers=_headers(access_token),
        params={"ids": ",".join(artist_ids[:50])},
        timeout=15.0,
    )
    response.raise_for_status()
    payload = response.json()
    items = payload.get("artists", []) if isinstance(payload, dict) else []
    return [item for item in items if isinstance(item, dict)]


def playlist_snapshot(access_token: str, playlist_id: str) -> dict[str, Any]:
    """Read playlist metadata and ordered track snapshots for historical import."""
    playlist_response = httpx.get(
        f"{SPOTIFY_API}/playlists/{playlist_id}", headers=_headers(access_token), timeout=15.0
    )
    playlist_response.raise_for_status()
    playlist = playlist_response.json()
    if not isinstance(playlist, dict) or not isinstance(playlist.get("name"), str):
        raise SpotifyError("Spotify returned an invalid playlist")
    items: list[dict[str, Any]] = []
    offset = 0
    while True:
        response = httpx.get(
            f"{SPOTIFY_API}/playlists/{playlist_id}/items",
            headers=_headers(access_token),
            params={"limit": 50, "offset": offset, "additional_types": "track"},
            timeout=15.0,
        )
        response.raise_for_status()
        page = response.json()
        if not isinstance(page, dict) or not isinstance(page.get("items"), list):
            raise SpotifyError("Spotify returned invalid playlist items")
        for item in page["items"]:
            track = item.get("track") if isinstance(item, dict) else None
            if (
                isinstance(track, dict)
                and track.get("type") == "track"
                and isinstance(track.get("id"), str)
                and isinstance(track.get("name"), str)
                and isinstance(track.get("uri"), str)
            ):
                items.append(track)
        if not page.get("next"):
            break
        offset += len(page["items"])
    return {"id": playlist_id, "name": playlist["name"], "items": items}


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


def delete_playlist(access_token: str, playlist_id: str) -> None:
    """Remove the playlist from the publisher's Spotify library.

    Spotify does not expose a true owner-delete API. Unfollowing is its
    supported deletion-equivalent and is preferable to leaving an empty private
    playlist behind after a local publication reversal.
    """
    response = httpx.delete(
        f"{SPOTIFY_API}/playlists/{playlist_id}/followers",
        headers=_headers(access_token),
        timeout=15.0,
    )
    response.raise_for_status()


# Refresh this long before Spotify says the token dies, so a request that
# starts at the edge of the window is not sent with a token that expires in
# flight.
TOKEN_REFRESH_MARGIN = timedelta(seconds=60)


def token_expiry(payload: dict[str, Any]) -> datetime | None:
    seconds = payload.get("expires_in")
    if not isinstance(seconds, int):
        return None
    return datetime.now(UTC) + timedelta(seconds=seconds) - TOKEN_REFRESH_MARGIN


def _headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
