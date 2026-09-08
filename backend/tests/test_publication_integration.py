"""PostgreSQL-backed tests for safe Spotify publication retries."""

from __future__ import annotations

import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.api.routes.admin import get_publication_status
from app.core.config import get_settings
from app.core.security import encrypt
from app.db.models import (
    AuditEvent,
    ExternalAccount,
    ExternalCredential,
    ExternalProvider,
    PlatformRole,
    Publication,
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
from app.services.publications import (
    PublicationError,
    defer_or_fail,
    execute_publication,
    execute_retirement,
    import_historical_playlist,
    start_publication,
    start_unpublish,
)


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
                spotify_uri=f"spotify:track:track-{suffix}-{index}",
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

        other_user = User(
            oidc_issuer="https://issuer.test",
            oidc_subject=f"other-publisher-{suffix}",
        )
        db.add(other_user)
        db.flush()
        other_account = ExternalAccount(
            user_id=other_user.id,
            provider=ExternalProvider.SPOTIFY,
            provider_subject=f"other-publisher-{suffix}",
        )
        db.add(other_account)
        db.commit()
        with pytest.raises(PublicationError, match="connected Spotify publisher"):
            start_publication(db, round_.id, other_account.id, publisher.id)

        publication = start_publication(db, round_.id, account.id, publisher.id)
        db.commit()
        db.refresh(round_)
        assert round_.publisher_account_id == account.id
        batches: list[list[str]] = []
        remote_track_ids: list[str] = []

        monkeypatch.setattr(spotify, "create_playlist", lambda *_: "playlist-id")
        monkeypatch.setattr(
            spotify,
            "playlist_snapshot",
            lambda *_: {
                "id": "playlist-id",
                "name": "Publication",
                "items": [{"id": track_id} for track_id in remote_track_ids],
            },
        )

        def fail_second_batch(_: str, __: str, uris: list[str]) -> None:
            batches.append(uris)
            if len(batches) == 2:
                raise spotify.SpotifyError("temporary provider failure")
            remote_track_ids.extend(uri.removeprefix("spotify:track:") for uri in uris)

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

        # Retrying is an explicit state transition performed by the admin route.
        publication.state = PublicationState.PUBLISHING
        round_.status = RoundStatus.PUBLISHING
        db.commit()

        def add_remaining(_: str, __: str, uris: list[str]) -> None:
            batches.append(uris)
            remote_track_ids.extend(uri.removeprefix("spotify:track:") for uri in uris)

        monkeypatch.setattr(spotify, "add_items", add_remaining)
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
        status = get_publication_status(round_.id, db, publisher)
        assert status is not None
        assert status["id"] == str(publication.id)
        assert status["state"] == "published"
        assert status["spotifyPlaylistId"] == "playlist-id"
        assert status["events"][0]["action"] == "publication.published"


def test_historical_playlist_import_preserves_order_without_remote_retirement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    suffix = uuid.uuid4().hex[:12]
    timestamp = datetime.now(UTC)
    with get_session_factory()() as db:
        admin = User(
            oidc_issuer="https://issuer.test",
            oidc_subject=f"importer-{suffix}",
            platform_role=PlatformRole.ADMIN,
        )
        series = Series(
            name=f"Import series {suffix}",
            slug=f"import-{suffix}",
            timezone="UTC",
            default_policies=[],
        )
        db.add_all((admin, series))
        db.flush()
        account = ExternalAccount(
            user_id=admin.id,
            provider=ExternalProvider.SPOTIFY,
            provider_subject=f"importer-{suffix}",
        )
        db.add(account)
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
        db.commit()

        item = {
            "id": f"import-track-{suffix}",
            "name": "Imported track",
            "uri": f"spotify:track:import{suffix}",
            "type": "track",
            "artists": [{"name": "The Archivists"}],
            "album": {"name": "An old album", "images": []},
            "explicit": False,
            "is_playable": True,
        }
        monkeypatch.setattr(
            spotify,
            "playlist_snapshot",
            lambda _token, _playlist_id: {
                "id": "old-playlist",
                "name": "Old playlist",
                "items": [item, item],
            },
        )
        imported = import_historical_playlist(
            db,
            series_id=series.id,
            publisher_account_id=account.id,
            spotify_playlist_id=f"old-playlist-{suffix}",
            opens_at=timestamp - timedelta(days=3),
            closes_at=timestamp - timedelta(days=2),
            published_at=timestamp - timedelta(days=1),
            actor_id=admin.id,
        )
        db.commit()

        publication = db.scalar(select(Publication).where(Publication.round_id == imported.id))
        assert publication is not None
        assert imported.status is RoundStatus.PUBLISHED
        assert publication.is_imported is True
        imported_items = list(
            db.scalars(
                select(PublicationItem)
                .where(PublicationItem.publication_id == publication.id)
                .order_by(PublicationItem.position)
            )
        )
        assert len(imported_items) == 2
        assert [item.position for item in imported_items] == [1, 2]
        assert all(item.contributor_id is None and item.submission_id is None for item in imported_items)
        with pytest.raises(PublicationError, match="historically imported"):
            start_unpublish(db, imported.id)


def test_only_latest_published_round_can_begin_unpublishing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    suffix = uuid.uuid4().hex[:12]
    now = datetime.now(UTC)
    with get_session_factory()() as db:
        publisher = User(
            oidc_issuer="https://issuer.test",
            oidc_subject=f"unpublish-{suffix}",
            platform_role=PlatformRole.ADMIN,
        )
        series = Series(
            name=f"Unpublish series {suffix}",
            slug=f"unpublish-{suffix}",
            timezone="UTC",
            default_policies=[],
        )
        db.add_all((publisher, series))
        db.flush()
        account = ExternalAccount(
            user_id=publisher.id,
            provider=ExternalProvider.SPOTIFY,
            provider_subject=f"unpublish-{suffix}",
        )
        db.add(account)
        db.flush()
        older = Round(
            series_id=series.id,
            title=f"Older {suffix}",
            timezone="UTC",
            submission_limit=0,
            opens_at=now - timedelta(days=6),
            closes_at=now - timedelta(days=5),
            publish_at=now - timedelta(days=4),
            status=RoundStatus.PUBLISHED,
            publisher_account_id=account.id,
            published_sequence=1,
            policy_snapshot=[],
        )
        latest = Round(
            series_id=series.id,
            title=f"Latest {suffix}",
            timezone="UTC",
            submission_limit=0,
            opens_at=now - timedelta(days=3),
            closes_at=now - timedelta(days=2),
            publish_at=now - timedelta(days=1),
            status=RoundStatus.PUBLISHED,
            publisher_account_id=account.id,
            published_sequence=2,
            policy_snapshot=[],
        )
        db.add_all((older, latest))
        db.flush()
        older_publication = Publication(
            round_id=older.id,
            publisher_account_id=account.id,
            state=PublicationState.PUBLISHED,
            spotify_playlist_id=f"older-{suffix}",
            idempotency_key=f"older-{suffix}",
        )
        latest_publication = Publication(
            round_id=latest.id,
            publisher_account_id=account.id,
            state=PublicationState.PUBLISHED,
            spotify_playlist_id=f"latest-{suffix}",
            idempotency_key=f"latest-{suffix}",
        )
        credential = ExternalCredential(
            external_account_id=account.id,
            ciphertext=encrypt(
                json.dumps({"access_token": "test-token"}),
                get_settings().credential_encryption_key.get_secret_value(),
            ),
            key_version="v1",
        )
        db.add_all((older_publication, latest_publication, credential))
        db.commit()

        with pytest.raises(PublicationError, match="most recently published"):
            start_unpublish(db, older.id)
        queued = start_unpublish(db, latest.id)
        assert queued.id == latest_publication.id
        assert queued.state is PublicationState.UNPUBLISHING
        assert latest.status is RoundStatus.UNPUBLISHING

        db.commit()
        monkeypatch.setattr(spotify, "delete_playlist", lambda _token, _playlist: None)
        execute_retirement(db, latest_publication.id)
        db.refresh(latest_publication)
        db.refresh(latest)
        assert latest_publication.state is PublicationState.UNPUBLISHED
        assert latest_publication.spotify_playlist_id is None
        assert latest.status is RoundStatus.CLOSED

        restarted = start_publication(db, latest.id, account.id, publisher.id)
        assert restarted.id == latest_publication.id
        assert restarted.state is PublicationState.PUBLISHING
        assert restarted.spotify_playlist_id is None


def test_concurrent_publication_requests_allocate_distinct_series_sequences() -> None:
    suffix = uuid.uuid4().hex[:12]
    now = datetime.now(UTC)
    with get_session_factory()() as db:
        publisher = User(
            oidc_issuer="https://issuer.test",
            oidc_subject=f"sequence-publisher-{suffix}",
        )
        series = Series(
            name=f"Sequences {suffix}",
            slug=f"sequences-{suffix}",
            timezone="UTC",
            default_policies=[],
        )
        db.add_all((publisher, series))
        db.flush()
        account = ExternalAccount(
            user_id=publisher.id,
            provider=ExternalProvider.SPOTIFY,
            provider_subject=f"sequence-publisher-{suffix}",
        )
        db.add(account)
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
        rounds = [
            Round(
                series_id=series.id,
                title=f"Concurrent {index} {suffix}",
                timezone="UTC",
                submission_limit=0,
                opens_at=now - timedelta(days=2),
                closes_at=now - timedelta(days=1),
                publish_at=now - timedelta(hours=12),
                status=RoundStatus.CLOSED,
                policy_snapshot=[],
            )
            for index in range(2)
        ]
        db.add_all(rounds)
        db.commit()
        round_ids = [round_.id for round_ in rounds]
        account_id, owner_id = account.id, publisher.id

    def publish(round_id: uuid.UUID) -> int:
        with get_session_factory()() as session:
            start_publication(session, round_id, account_id, owner_id)
            session.commit()
            value = session.get(Round, round_id)
            assert value is not None and value.published_sequence is not None
            return value.published_sequence

    with ThreadPoolExecutor(max_workers=2) as executor:
        sequences = list(executor.map(publish, round_ids))

    assert sorted(sequences) == [1, 2]


def test_enqueue_failure_marks_the_publication_failed_for_ui_retry() -> None:
    suffix = uuid.uuid4().hex[:12]
    now = datetime.now(UTC)
    with get_session_factory()() as db:
        user = User(oidc_issuer="https://issuer.test", oidc_subject=f"queue-{suffix}")
        series = Series(
            name=f"Queue {suffix}", slug=f"queue-{suffix}", timezone="UTC", default_policies=[]
        )
        db.add_all((user, series))
        db.flush()
        account = ExternalAccount(
            user_id=user.id,
            provider=ExternalProvider.SPOTIFY,
            provider_subject=f"queue-{suffix}",
        )
        round_ = Round(
            series_id=series.id,
            title=f"Queue {suffix}",
            timezone="UTC",
            submission_limit=0,
            opens_at=now - timedelta(days=2),
            closes_at=now - timedelta(days=1),
            publish_at=now - timedelta(hours=12),
            status=RoundStatus.PUBLISHING,
            policy_snapshot=[],
        )
        db.add_all((account, round_))
        db.flush()
        publication = Publication(
            round_id=round_.id,
            publisher_account_id=account.id,
            state=PublicationState.PUBLISHING,
            idempotency_key=f"queue-{suffix}",
        )
        db.add(publication)
        db.commit()

        def rejected(_: str) -> None:
            raise RuntimeError("queue unavailable")

        defer_or_fail(db, publication, round_, rejected)
        db.refresh(publication)
        db.refresh(round_)
        assert publication.state is PublicationState.FAILED
        assert round_.status is RoundStatus.FAILED
        assert publication.last_error is not None and "Retry" in publication.last_error
