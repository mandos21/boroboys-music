"""PostgreSQL-backed tests for monotonic listening-evidence caching."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

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


def test_stale_evidence_refresh_keeps_the_stronger_playcount(monkeypatch: pytest.MonkeyPatch) -> None:
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
