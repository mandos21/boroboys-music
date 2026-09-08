"""PostgreSQL-backed tests for monotonic listening-evidence caching."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.db.models import ExternalAccount, ExternalProvider, ListeningEvidence, Track, User
from app.db.session import get_session_factory
from app.services import evidence


def test_fresh_evidence_avoids_a_remote_refresh(monkeypatch: pytest.MonkeyPatch) -> None:
    suffix = uuid.uuid4().hex[:12]
    with get_session_factory()() as db:
        user = User(oidc_issuer="https://issuer.test", oidc_subject=f"listener-{suffix}")
        db.add(user)
        db.flush()
        account = ExternalAccount(
            user_id=user.id,
            provider=ExternalProvider.LASTFM,
            provider_subject=f"listener-{suffix}",
        )
        track = Track(
            spotify_track_id=f"evidence-{suffix}",
            name="Already heard",
            artist="The Cache",
        )
        db.add_all((account, track))
        db.flush()
        evidence_row = ListeningEvidence(
            external_account_id=account.id,
            track_id=track.id,
            source="lastfm",
            playcount=4,
            match_confidence="exact",
            response_status="available",
            refresh_after=datetime.now(UTC) + timedelta(hours=1),
        )
        db.add(evidence_row)
        db.commit()

        def unexpected_request(*_args: object, **_kwargs: object) -> None:
            raise AssertionError("fresh evidence should not call Last.fm")

        monkeypatch.setattr(evidence.httpx, "get", unexpected_request)
        evidence._refresh_account(db, account, track)

        assert evidence_row.playcount == 4


def test_stale_evidence_refresh_keeps_the_stronger_playcount(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    suffix = uuid.uuid4().hex[:12]
    with get_session_factory()() as db:
        user = User(oidc_issuer="https://issuer.test", oidc_subject=f"stale-{suffix}")
        db.add(user)
        db.flush()
        account = ExternalAccount(
            user_id=user.id,
            provider=ExternalProvider.LASTFM,
            provider_subject=f"stale-{suffix}",
        )
        track = Track(
            spotify_track_id=f"stale-evidence-{suffix}",
            name="Monotonic",
            artist="The Cache",
        )
        db.add_all((account, track))
        db.flush()
        row = ListeningEvidence(
            external_account_id=account.id,
            track_id=track.id,
            source="lastfm",
            playcount=7,
            match_confidence="exact",
            response_status="available",
            refresh_after=datetime.now(UTC) - timedelta(seconds=1),
        )
        db.add(row)
        db.commit()

        class Response:
            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict[str, object]:
                return {"track": {"userplaycount": "2"}}

        monkeypatch.setattr(evidence.httpx, "get", lambda *_args, **_kwargs: Response())
        evidence._refresh_account(db, account, track)

        assert row.playcount == 7
        assert row.refresh_after is not None and row.refresh_after > datetime.now(UTC)


def test_refresh_caches_track_artist_and_album_counts(monkeypatch: pytest.MonkeyPatch) -> None:
    suffix = uuid.uuid4().hex[:12]
    with get_session_factory()() as db:
        user = User(oidc_issuer="https://issuer.test", oidc_subject=f"breakdown-{suffix}")
        db.add(user)
        db.flush()
        account = ExternalAccount(
            user_id=user.id,
            provider=ExternalProvider.LASTFM,
            provider_subject=f"breakdown-{suffix}",
        )
        track = Track(
            spotify_track_id=f"breakdown-track-{suffix}",
            name="Breakdown",
            artist="The Cache",
            album="Details",
        )
        db.add_all((account, track))
        db.commit()

        class Response:
            def __init__(self, method: str) -> None:
                self.method = method

            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict[str, object]:
                key = self.method.split(".")[0]
                count = {"track": "3", "artist": "11", "album": "7"}[key]
                return {key: {"userplaycount": count}}

        def fake_get(*_args: object, **kwargs: object) -> Response:
            params = kwargs["params"]
            assert isinstance(params, dict)
            return Response(str(params["method"]))

        monkeypatch.setattr(evidence.httpx, "get", fake_get)
        evidence._refresh_account(db, account, track)
        db.commit()

        row = db.scalar(
            select(ListeningEvidence).where(
                ListeningEvidence.external_account_id == account.id,
                ListeningEvidence.track_id == track.id,
            )
        )
        assert row is not None
        assert (row.playcount, row.artist_playcount, row.album_playcount) == (3, 11, 7)


def test_a_lastfm_error_payload_is_not_cached_as_zero_plays(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Last.fm reports "not found" inside a 200 response, not as an HTTP status."""
    suffix = uuid.uuid4().hex[:12]
    with get_session_factory()() as db:
        user = User(oidc_issuer="https://issuer.test", oidc_subject=f"unmatched-{suffix}")
        db.add(user)
        db.flush()
        account = ExternalAccount(
            user_id=user.id,
            provider=ExternalProvider.LASTFM,
            provider_subject=f"unmatched-{suffix}",
        )
        track = Track(
            spotify_track_id=f"unmatched-evidence-{suffix}",
            name="Nothing Last.fm knows about",
            artist="The Unknowns",
        )
        db.add_all((account, track))
        db.flush()
        db.commit()

        class Response:
            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict[str, object]:
                return {"error": 6, "message": "Track not found"}

        monkeypatch.setattr(evidence.httpx, "get", lambda *_args, **_kwargs: Response())
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
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    suffix = uuid.uuid4().hex[:12]
    with get_session_factory()() as db:
        user = User(oidc_issuer="https://issuer.test", oidc_subject=f"retained-{suffix}")
        db.add(user)
        db.flush()
        account = ExternalAccount(
            user_id=user.id,
            provider=ExternalProvider.LASTFM,
            provider_subject=f"retained-{suffix}",
        )
        track = Track(
            spotify_track_id=f"retained-evidence-{suffix}",
            name="Previously matched",
            artist="The Cache",
        )
        db.add_all((account, track))
        db.flush()
        row = ListeningEvidence(
            external_account_id=account.id,
            track_id=track.id,
            source="lastfm",
            playcount=9,
            match_confidence="exact",
            response_status="available",
            refresh_after=datetime.now(UTC) - timedelta(seconds=1),
        )
        db.add(row)
        db.commit()

        class Response:
            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict[str, object]:
                return {"error": 6, "message": "Track not found"}

        monkeypatch.setattr(evidence.httpx, "get", lambda *_args, **_kwargs: Response())
        evidence._refresh_account(db, account, track)

        assert row.playcount == 9
        assert row.match_confidence == "exact"
        assert row.response_status == "available"
