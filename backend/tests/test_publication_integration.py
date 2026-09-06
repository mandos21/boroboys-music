"""PostgreSQL-backed tests for safe Spotify publication retries."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.security import encrypt
from app.db.models import (
    AuditEvent,
    ExternalAccount,
    ExternalCredential,
    ExternalProvider,
    PlatformRole,
    PublicationItem,
    PublicationState,
    Round,
    RoundStatus,
    Series,
    Submission,
    SubmissionStatus,
    Track,
    User,
)
from app.db.session import get_session_factory
from app.services import spotify
from app.services.publications import execute_publication, start_publication


def test_retry_resumes_after_a_committed_spotify_batch(monkeypatch: pytest.MonkeyPatch) -> None:
    suffix = uuid.uuid4().hex[:12]
    now = datetime.now(UTC)
    with get_session_factory()() as db:
        publisher = User(
            oidc_issuer="https://issuer.test",
            oidc_subject=f"publisher-{suffix}",
            platform_role=PlatformRole.ADMIN,
        )
        series = Series(
            name=f"Publication series {suffix}",
            slug=f"publication-{suffix}",
            timezone="UTC",
            default_policies=[],
            auto_start_next_round=False,
        )
        db.add_all((publisher, series))
        db.flush()
        account = ExternalAccount(
            user_id=publisher.id,
            provider=ExternalProvider.SPOTIFY,
            provider_subject=f"publisher-{suffix}",
            display_name="Publisher",
        )
        round_ = Round(
            series_id=series.id,
            title=f"Publication round {suffix}",
            timezone="UTC",
            submission_limit=200,
            opens_at=now - timedelta(days=2),
            closes_at=now - timedelta(days=1),
            publish_at=now - timedelta(hours=12),
            status=RoundStatus.CLOSED,
            policy_snapshot=[],
        )
        db.add_all((account, round_))
        db.flush()
        db.add(
            ExternalCredential(
                external_account_id=account.id,
                ciphertext=encrypt(
                    json.dumps({"access_token": "test-token"}),
                    get_settings().credential_encryption_key.get_secret_value(),
                ),
                key_version="v1",
            )
        )
        tracks = [
            Track(
                spotify_track_id=f"track-{suffix}-{index}",
                name=f"Track {index}",
                artist="The Testers",
                spotify_uri=f"spotify:track:{suffix}{index}",
            )
            for index in range(101)
        ]
        db.add_all(tracks)
        db.flush()
        db.add_all(
            Submission(
                round_id=round_.id,
                contributor_id=publisher.id,
                track_id=track.id,
                status=SubmissionStatus.ACCEPTED,
            )
            for track in tracks
        )
        db.commit()

        publication = start_publication(db, round_.id, account.id)
        db.commit()
        db.refresh(round_)
        assert round_.publisher_account_id == account.id
        batches: list[list[str]] = []

        monkeypatch.setattr(spotify, "create_playlist", lambda *_: "playlist-id")

        def fail_second_batch(_: str, __: str, uris: list[str]) -> None:
            batches.append(uris)
            if len(batches) == 2:
                raise spotify.SpotifyError("temporary provider failure")

        monkeypatch.setattr(spotify, "add_items", fail_second_batch)
        execute_publication(db, publication.id)

        db.refresh(publication)
        assert publication.state is PublicationState.FAILED
        assert [len(batch) for batch in batches] == [100, 1]
        assert (
            db.scalar(
                select(func.count())
                .select_from(PublicationItem)
                .where(
                    PublicationItem.publication_id == publication.id,
                    PublicationItem.published_at.is_not(None),
                )
            )
            == 100
        )

        monkeypatch.setattr(spotify, "add_items", lambda _token, _playlist, uris: batches.append(uris))
        execute_publication(db, publication.id)

        db.refresh(publication)
        assert publication.state is PublicationState.PUBLISHED
        assert [len(batch) for batch in batches] == [100, 1, 1]
        assert (
            db.scalar(
                select(func.count())
                .select_from(PublicationItem)
                .where(
                    PublicationItem.publication_id == publication.id,
                    PublicationItem.published_at.is_not(None),
                )
            )
            == 101
        )
        assert (
            db.scalar(
                select(func.count()).select_from(AuditEvent).where(
                    AuditEvent.target_id == publication.id,
                    AuditEvent.action == "publication.published",
                )
            )
            == 1
        )
