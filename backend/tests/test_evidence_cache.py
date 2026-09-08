"""PostgreSQL-backed tests for monotonic listening-evidence caching."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ExternalAccount, ListeningEvidence, Track, User
from app.services import evidence


class _Response:
    """A Last.fm reply that has already succeeded at the HTTP level."""

    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return self._payload


def _answer(monkeypatch: pytest.MonkeyPatch, payload: dict[str, object]) -> None:
    monkeypatch.setattr(evidence.httpx, "get", lambda *_a, **_k: _Response(payload))


def _cached(
    db: Session, account: ExternalAccount, track: Track, *, stale: bool, **values: object
) -> ListeningEvidence:
    row = ListeningEvidence(
        external_account_id=account.id,
        track_id=track.id,
        source="lastfm",
        match_confidence="exact",
        response_status="available",
        refresh_after=datetime.now(UTC) + (timedelta(seconds=-1) if stale else timedelta(hours=1)),
        **values,
    )
    db.add(row)
    db.commit()
    return row


def test_fresh_evidence_avoids_a_remote_refresh(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
    make_user: Callable[..., User],
    make_lastfm_account: Callable[..., ExternalAccount],
    make_track: Callable[..., Track],
) -> None:
    account = make_lastfm_account(make_user())
    track = make_track(name="Already heard", artist="The Cache")
    row = _cached(db, account, track, stale=False, playcount=4)

    def unexpected_request(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("fresh evidence should not call Last.fm")

    monkeypatch.setattr(evidence.httpx, "get", unexpected_request)
    assert evidence._refresh_account(db, account, track) is False
    assert row.playcount == 4


def test_stale_evidence_refresh_keeps_the_stronger_playcount(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
    make_user: Callable[..., User],
    make_lastfm_account: Callable[..., ExternalAccount],
    make_track: Callable[..., Track],
) -> None:
    account = make_lastfm_account(make_user())
    track = make_track(name="Monotonic", artist="The Cache")
    row = _cached(db, account, track, stale=True, playcount=7)

    _answer(monkeypatch, {"track": {"userplaycount": "2"}})
    evidence._refresh_account(db, account, track)

    assert row.playcount == 7
    assert row.refresh_after is not None and row.refresh_after > datetime.now(UTC)


def test_refresh_caches_track_artist_and_album_counts(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
    make_user: Callable[..., User],
    make_lastfm_account: Callable[..., ExternalAccount],
    make_track: Callable[..., Track],
) -> None:
    account = make_lastfm_account(make_user())
    track = make_track(name="Counted", artist="The Cache", album="The Album")
    counts = {"track": 3, "artist": 11, "album": 5}
    monkeypatch.setattr(
        evidence.httpx,
        "get",
        lambda *_a, **kwargs: _Response(
            {
                key: {"userplaycount": value}
                for key, value in counts.items()
                if kwargs["params"]["method"].startswith(key)
            }
        ),
    )
    evidence._refresh_account(db, account, track)
    db.flush()

    row = db.scalar(
        select(ListeningEvidence).where(ListeningEvidence.external_account_id == account.id)
    )
    assert row is not None
    assert (row.playcount, row.artist_playcount, row.album_playcount) == (3, 11, 5)


def test_a_lastfm_error_payload_is_not_cached_as_zero_plays(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
    make_user: Callable[..., User],
    make_lastfm_account: Callable[..., ExternalAccount],
    make_track: Callable[..., Track],
) -> None:
    """Last.fm reports "not found" inside a 200 response, not as an HTTP status."""
    account = make_lastfm_account(make_user())
    track = make_track(name="Nothing Last.fm knows about", artist="The Unknowns")

    _answer(monkeypatch, {"error": 6, "message": "Track not found"})
    assert evidence._refresh_account(db, account, track) is True
    db.flush()

    row = db.scalar(
        select(ListeningEvidence).where(ListeningEvidence.external_account_id == account.id)
    )
    assert row is not None
    assert row.playcount is None
    assert row.match_confidence == "unmatched"
    assert row.response_status == "unmatched"


def test_an_unmatched_response_never_downgrades_existing_evidence(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
    make_user: Callable[..., User],
    make_lastfm_account: Callable[..., ExternalAccount],
    make_track: Callable[..., Track],
) -> None:
    account = make_lastfm_account(make_user())
    track = make_track(name="Previously matched", artist="The Cache")
    row = _cached(db, account, track, stale=True, playcount=9)

    _answer(monkeypatch, {"error": 6, "message": "Track not found"})
    evidence._refresh_account(db, account, track)

    assert row.playcount == 9
    assert row.match_confidence == "exact"
    assert row.response_status == "available"
