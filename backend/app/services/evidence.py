"""Additive Last.fm listening-evidence caching."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.models import ExternalAccount, ExternalProvider, ListeningEvidence, RoundMember, Track


class LastfmUnmatched(Exception):
    """Last.fm answered successfully but knows nothing about this track."""


def refresh_round_evidence(db: Session, round_id: str, track_id: str) -> int:
    """Refresh linked Last.fm accounts; retain older positive evidence on failures."""
    settings = get_settings()
    if not settings.lastfm_api_key:
        return 0
    accounts = list(
        db.scalars(
            select(ExternalAccount)
            .join(RoundMember, RoundMember.user_id == ExternalAccount.user_id)
            .where(
                RoundMember.round_id == round_id,
                RoundMember.removed_at.is_(None),
                ExternalAccount.provider == ExternalProvider.LASTFM,
                ExternalAccount.is_active.is_(True),
            )
        )
    )
    track = db.get(Track, track_id)
    if track is None:
        return 0
    refreshed = sum(_refresh_account(db, account, track) for account in accounts)
    db.commit()
    return refreshed


def _refresh_account(db: Session, account: ExternalAccount, track: Track) -> bool:
    """Return whether this account's evidence was actually refetched."""
    settings = get_settings()
    now = datetime.now(UTC)
    evidence = db.scalar(
        select(ListeningEvidence).where(
            ListeningEvidence.external_account_id == account.id,
            ListeningEvidence.track_id == track.id,
            ListeningEvidence.source == "lastfm",
        )
    )
    # A listening history only grows.  Fresh cached evidence is therefore a
    # useful answer even though it may not yet include the newest plays.
    if evidence is not None and evidence.refresh_after is not None and evidence.refresh_after > now:
        return False
    try:
        playcount = _lastfm_playcount(settings, account.provider_subject, "track.getInfo", track)
    except LastfmUnmatched:
        # Last.fm has no entry matching this artist/track pair. Recording that
        # as zero plays would be indistinguishable from a real zero, so the
        # absence of a match is stored as its own outcome.
        playcount = None
    except (httpx.HTTPError, ValueError, TypeError):
        if evidence is not None:
            evidence.refresh_after = now + timedelta(hours=1)
        return False
    artist_playcount = _optional_lastfm_playcount(
        settings, account.provider_subject, "artist.getInfo", track
    )
    album_playcount = (
        _optional_lastfm_playcount(settings, account.provider_subject, "album.getInfo", track)
        if track.album
        else None
    )
    # Listening data is monotonic. Never replace a stronger cached positive
    # result, and describe the merged row rather than only this one response.
    merged_playcount = _highest_count(evidence.playcount if evidence else None, playcount)
    matched = merged_playcount is not None
    values = {
        "playcount": merged_playcount,
        "artist_playcount": _highest_count(
            evidence.artist_playcount if evidence else None, artist_playcount
        ),
        "album_playcount": _highest_count(
            evidence.album_playcount if evidence else None, album_playcount
        ),
        "match_confidence": "exact" if matched else "unmatched",
        "fetched_at": now,
        "refresh_after": now + timedelta(hours=settings.lastfm_evidence_refresh_hours),
        "response_status": "available" if matched else "unmatched",
    }
    if evidence is None:
        db.add(
            ListeningEvidence(
                external_account_id=account.id,
                track_id=track.id,
                source="lastfm",
                **values,
            )
        )
    else:
        for key, value in values.items():
            setattr(evidence, key, value)
    return True


def _lastfm_playcount(settings: Settings, username: str, method: str, track: Track) -> int:
    api_key = settings.lastfm_api_key
    response = httpx.get(
        "https://ws.audioscrobbler.com/2.0/",
        params={
            "method": method,
            "api_key": api_key.get_secret_value() if api_key else "",
            "user": username,
            "artist": track.artist,
            **({"track": track.name} if method == "track.getInfo" else {}),
            **({"album": track.album} if method == "album.getInfo" and track.album else {}),
            "format": "json",
        },
        timeout=10.0,
    )
    response.raise_for_status()
    payload = response.json()
    # Last.fm reports "not found" and several other conditions as an error
    # object inside a 200 response, so the status code alone proves nothing.
    if isinstance(payload, dict) and "error" in payload:
        raise LastfmUnmatched(str(payload.get("message", "Last.fm returned an error")))
    return _playcount(payload, method.split(".")[0])


def _optional_lastfm_playcount(settings: Settings, username: str, method: str, track: Track) -> int | None:
    try:
        return _lastfm_playcount(settings, username, method, track)
    except (httpx.HTTPError, LastfmUnmatched, ValueError, TypeError):
        return None


def _highest_count(previous: int | None, fresh: int | None) -> int | None:
    values = [value for value in (previous, fresh) if value is not None]
    return max(values) if values else None


def _playcount(payload: object, key: str = "track") -> int:
    if not isinstance(payload, dict):
        return 0
    item = payload.get(key)
    if not isinstance(item, dict):
        return 0
    raw = item.get("userplaycount", 0)
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return 0
