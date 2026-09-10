"""Last.fm web authentication and signed session exchange."""

from __future__ import annotations

import hashlib
from urllib.parse import urlencode

import httpx

from app.core.config import Settings

API_URL = "https://ws.audioscrobbler.com/2.0/"
AUTH_URL = "https://www.last.fm/api/auth/"


class LastfmError(Exception):
    pass


def monthly_top_tracks(
    settings: Settings, username: str, limit: int = 8
) -> list[dict[str, str | None]]:
    """Return a listener's recent top tracks for voluntary submission suggestions."""
    if not settings.lastfm_api_key:
        raise LastfmError("Last.fm is not configured")
    response = httpx.get(
        API_URL,
        params={
            "method": "user.getTopTracks",
            "api_key": settings.lastfm_api_key.get_secret_value(),
            "user": username,
            "period": "1month",
            "limit": limit,
            "format": "json",
        },
        timeout=10.0,
    )
    response.raise_for_status()
    payload = response.json()
    container = payload.get("toptracks") if isinstance(payload, dict) else None
    rows = container.get("track") if isinstance(container, dict) else None
    if not isinstance(rows, list):
        return []
    suggestions: list[dict[str, str | None]] = []
    for item in rows:
        artist = item.get("artist") if isinstance(item, dict) else None
        artist_name = artist.get("name") if isinstance(artist, dict) else None
        name = item.get("name") if isinstance(item, dict) else None
        if isinstance(name, str) and isinstance(artist_name, str):
            images = item.get("image")
            artwork_url = None
            if isinstance(images, list):
                image_urls = [image.get("#text") for image in images if isinstance(image, dict)]
                artwork_url = next(
                    (url for url in reversed(image_urls) if isinstance(url, str) and url), None
                )
            suggestions.append({"name": name, "artist": artist_name, "artworkUrl": artwork_url})
    return suggestions


def genre_tags(settings: Settings, artist: str, track: str, limit: int = 8) -> list[str]:
    """Return Last.fm's top tags for a track, falling back to the artist's.

    Last.fm tags are free-form crowd labels, not a controlled genre list - a
    typical track carries a mix of genuine genres ("dream pop") alongside
    moods, decades, and personal tags ("seen live", "favourites"). Filtering
    happens in the caller, against the same taxonomy Spotify genres already
    run through, so only terms it recognises as a genre survive either source.
    """
    if not settings.lastfm_api_key:
        raise LastfmError("Last.fm is not configured")
    api_key = settings.lastfm_api_key.get_secret_value()
    tags = _top_tags(api_key, {"method": "track.getTopTags", "artist": artist, "track": track})
    if not tags:
        tags = _top_tags(api_key, {"method": "artist.getTopTags", "artist": artist})
    return tags[:limit]


def _top_tags(api_key: str, params: dict[str, str]) -> list[str]:
    response = httpx.get(
        API_URL,
        params={**params, "api_key": api_key, "format": "json"},
        timeout=10.0,
    )
    response.raise_for_status()
    payload = response.json()
    container = payload.get("toptags") if isinstance(payload, dict) else None
    rows = container.get("tag") if isinstance(container, dict) else None
    if not isinstance(rows, list):
        return []
    names = [row.get("name") for row in rows if isinstance(row, dict)]
    return [name.strip() for name in names if isinstance(name, str) and name.strip()]


def authorization_url(settings: Settings, state: str) -> str:
    callback = f"{settings.lastfm_callback_url}?{urlencode({'state': state})}"
    api_key = settings.lastfm_api_key.get_secret_value() if settings.lastfm_api_key else ""
    return f"{AUTH_URL}?{urlencode({'api_key': api_key, 'cb': callback})}"


def exchange_session(settings: Settings, token: str) -> dict[str, str]:
    if not settings.lastfm_api_key or not settings.lastfm_shared_secret:
        raise LastfmError("Last.fm is not configured")
    params = {
        "method": "auth.getSession",
        "api_key": settings.lastfm_api_key.get_secret_value(),
        "token": token,
    }
    params["api_sig"] = _signature(params, settings.lastfm_shared_secret.get_secret_value())
    response = httpx.get(API_URL, params={**params, "format": "json"}, timeout=15.0)
    response.raise_for_status()
    payload = response.json()
    session = payload.get("session") if isinstance(payload, dict) else None
    if (
        not isinstance(session, dict)
        or not isinstance(session.get("name"), str)
        or not isinstance(session.get("key"), str)
    ):
        raise LastfmError("Last.fm returned no session")
    return {"username": session["name"], "session_key": session["key"]}


def _signature(params: dict[str, str], secret: str) -> str:
    material = "".join(f"{key}{params[key]}" for key in sorted(params)) + secret
    return hashlib.md5(material.encode("utf-8")).hexdigest()  # noqa: S324 -- required by Last.fm protocol
