"""Additive Last.fm listening-evidence caching."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import ExternalAccount, ExternalProvider, ListeningEvidence, RoundMember, Track


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
    refreshed = 0
    for account in accounts:
        _refresh_account(db, account, track)
        refreshed += 1
    db.commit()
    return refreshed


def _refresh_account(db: Session, account: ExternalAccount, track: Track) -> None:
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
        return
    try:
        response = httpx.get(
            "https://ws.audioscrobbler.com/2.0/",
            params={
                "method": "track.getInfo",
                "api_key": settings.lastfm_api_key.get_secret_value()
                if settings.lastfm_api_key
                else "",
                "user": account.provider_subject,
                "artist": track.artist,
                "track": track.name,
                "format": "json",
            },
            timeout=10.0,
        )
        response.raise_for_status()
        payload = response.json()
        playcount = _playcount(payload)
    except (httpx.HTTPError, ValueError, TypeError):
        if evidence is not None:
            evidence.refresh_after = now + timedelta(hours=1)
        return
    values = {
        "playcount": playcount,
        "match_confidence": "exact",
        "fetched_at": now,
        "refresh_after": now + timedelta(hours=settings.lastfm_evidence_refresh_hours),
        "response_status": "available",
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
        # Listening data is monotonic. Never replace a stronger cached positive result.
        evidence.playcount = max(
            value for value in (evidence.playcount, playcount) if value is not None
        )
        for key, value in values.items():
            if key != "playcount":
                setattr(evidence, key, value)


def _playcount(payload: object) -> int:
    if not isinstance(payload, dict):
        return 0
    track = payload.get("track")
    if not isinstance(track, dict):
        return 0
    raw = track.get("userplaycount", 0)
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return 0
