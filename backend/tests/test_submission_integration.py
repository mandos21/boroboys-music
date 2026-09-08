"""PostgreSQL-backed acceptance coverage for the contributor submission flow."""

from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.routes.rounds import (
    SubmissionCreate,
    SubmissionDraftUpdate,
    SubmissionUpdate,
    TrackEvaluationRequest,
    TrackInput,
    create_submission,
    evaluate_track,
    get_submission_draft,
    save_submission_draft,
    update_submission,
)
from app.api.routes.rounds import submissions as submission_routes
from app.core.config import get_settings
from app.core.security import encrypt
from app.db.models import (
    EvaluationDecision,
    ExternalAccount,
    ExternalCredential,
    ExternalProvider,
    PlatformRole,
    PolicyEvaluation,
    Round,
    RoundMember,
    RoundStatus,
    Series,
    Submission,
    SubmissionStatus,
    Track,
    User,
)
from app.db.session import get_session_factory
from app.services import spotify
from app.services.policies import evaluate_submission
from app.tasks import app as task_app


@pytest.fixture
def opened_task_app() -> None:
    task_app.open()
    try:
        yield
    finally:
        task_app.close()


@pytest.fixture(autouse=True)
def canonical_track_lookup(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep policy-flow tests independent from Spotify's transport adapter."""
    monkeypatch.setattr(
        submission_routes, "_canonical_track_input", lambda _db, _user, track: track
    )


def test_canonical_track_lookup_uses_spotify_not_browser_metadata(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A browser cannot alter the data policies and publications rely on."""
    monkeypatch.undo()  # Exercise the real helper instead of the policy-test fixture.
    suffix = uuid.uuid4().hex[:12]
    user = User(oidc_issuer="https://issuer.test", oidc_subject=f"canonical-{suffix}")
    db.add(user)
    db.flush()
    account = ExternalAccount(
        user_id=user.id,
        provider=ExternalProvider.SPOTIFY,
        provider_subject=f"canonical-{suffix}",
    )
    db.add(account)
    db.flush()
    db.add(
        ExternalCredential(
            external_account_id=account.id,
            ciphertext=encrypt(
                '{"access_token": "spotify-access-token"}',
                get_settings().credential_encryption_key.get_secret_value(),
            ),
            key_version="v1",
        )
    )
    db.commit()

    monkeypatch.setattr(
        spotify,
        "tracks_by_id",
        lambda token, track_ids: [
            {
                "id": track_ids[0],
                "name": "Trusted title",
                "uri": f"spotify:track:{track_ids[0]}",
                "artists": [{"name": "Trusted artist"}],
                "album": {
                    "name": "Trusted album",
                    "images": [{"url": "https://images.test/trusted.jpg"}],
                },
                "explicit": True,
                "is_playable": True,
            }
        ],
    )
    canonical = submission_routes._canonical_track_input(
        db,
        user,
        TrackInput(
            spotify_track_id=f"canonical-track-{suffix}",
            name="Browser-controlled title",
            artist="Browser-controlled artist",
            album="Browser-controlled album",
            artwork_url="https://attacker.test/art.jpg",
            provider_metadata={"explicit": False},
        ),
    )

    assert canonical.name == "Trusted title"
    assert canonical.artist == "Trusted artist"
    assert canonical.album == "Trusted album"
    assert canonical.artwork_url == "https://images.test/trusted.jpg"
    assert canonical.provider_metadata == {"explicit": True, "isPlayable": True}


def test_canonical_track_collects_artist_genres_without_trusting_the_browser(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.undo()
    suffix = uuid.uuid4().hex[:12]
    user = User(oidc_issuer="https://issuer.test", oidc_subject=f"genre-{suffix}")
    db.add(user)
    db.flush()
    account = ExternalAccount(
        user_id=user.id,
        provider=ExternalProvider.SPOTIFY,
        provider_subject=f"genre-{suffix}",
    )
    db.add(account)
    db.flush()
    db.add(
        ExternalCredential(
            external_account_id=account.id,
            ciphertext=encrypt(
                '{"access_token": "spotify-access-token"}',
                get_settings().credential_encryption_key.get_secret_value(),
            ),
            key_version="v1",
        )
    )
    db.commit()
    monkeypatch.setattr(
        spotify,
        "tracks_by_id",
        lambda _token, track_ids: [
            {
                "id": track_ids[0],
                "name": "Trusted title",
                "uri": f"spotify:track:{track_ids[0]}",
                "artists": [{"id": "artist-1", "name": "Trusted artist"}],
            }
        ],
    )
    monkeypatch.setattr(
        spotify,
        "artists_by_id",
        lambda _token, artist_ids: [{"id": artist_ids[0], "genres": ["dream pop", "indie"]}],
    )

    canonical = submission_routes._canonical_track_input(
        db,
        user,
        TrackInput(spotify_track_id=f"genre-track-{suffix}", name="Browser", artist="Browser"),
    )

    assert canonical.provider_metadata["genres"] == ["dream pop", "indie"]


def test_warning_requires_confirmation_and_persists_an_audit_record(
    db: Session, opened_task_app: None
) -> None:
    """A real transaction cannot turn a warning into an accepted submission by accident."""
    suffix = uuid.uuid4().hex[:12]
    now = datetime.now(UTC)
    contributor = User(
        oidc_issuer="https://issuer.test",
        oidc_subject=f"contributor-{suffix}",
        display_name="Contributor",
        platform_role=PlatformRole.MEMBER,
    )
    series = Series(
        name=f"Integration series {suffix}",
        slug=f"integration-{suffix}",
        timezone="UTC",
        default_policies=[],
    )
    db.add_all((contributor, series))
    db.flush()
    round_ = Round(
        series_id=series.id,
        title=f"Integration round {suffix}",
        timezone="UTC",
        submission_limit=1,
        opens_at=now - timedelta(minutes=5),
        closes_at=now + timedelta(minutes=5),
        publish_at=now + timedelta(minutes=10),
        status=RoundStatus.OPEN,
        policy_snapshot=[{"kind": "editorial_warning", "on_match": "warn"}],
    )
    db.add(round_)
    db.flush()
    db.add(RoundMember(round_id=round_.id, user_id=contributor.id))
    db.commit()

    track = TrackInput(
        spotify_track_id=f"track-{suffix}",
        name="A warning track",
        artist="The Testers",
        spotify_uri=f"spotify:track:{suffix}",
    )
    preflight = evaluate_track(round_.id, TrackEvaluationRequest(track=track), db, contributor)
    assert preflight["canSubmit"] is True
    assert preflight["requiresWarningConfirmation"] is True
    assert preflight["limitRemaining"] == 1

    unconfirmed = create_submission(round_.id, SubmissionCreate(track=track), db, contributor)
    assert unconfirmed["accepted"] is False
    assert unconfirmed["requiresWarningConfirmation"] is True
    assert (
        db.scalar(
            select(func.count()).select_from(Submission).where(Submission.round_id == round_.id)
        )
        == 0
    )

    confirmed = create_submission(
        round_.id,
        SubmissionCreate(track=track, confirm_warnings=True),
        db,
        contributor,
    )
    assert confirmed["accepted"] is True
    assert (
        db.scalar(
            select(func.count()).select_from(Submission).where(Submission.round_id == round_.id)
        )
        == 1
    )
    decision = db.scalar(
        select(PolicyEvaluation.decision).where(PolicyEvaluation.round_id == round_.id)
    )
    assert decision is EvaluationDecision.WARN


def test_track_replacement_rechecks_policies_and_preserves_prior_evaluations(
    db: Session,
    opened_task_app: None,
) -> None:
    suffix = uuid.uuid4().hex[:12]
    now = datetime.now(UTC)
    contributor = User(
        oidc_issuer="https://issuer.test",
        oidc_subject=f"replacement-{suffix}",
        platform_role=PlatformRole.MEMBER,
    )
    series = Series(
        name=f"Replacement series {suffix}",
        slug=f"replacement-{suffix}",
        timezone="UTC",
        default_policies=[],
    )
    db.add_all((contributor, series))
    db.flush()
    round_ = Round(
        series_id=series.id,
        title=f"Replacement round {suffix}",
        timezone="UTC",
        submission_limit=1,
        opens_at=now - timedelta(minutes=5),
        closes_at=now + timedelta(minutes=5),
        publish_at=now + timedelta(minutes=10),
        status=RoundStatus.OPEN,
        policy_snapshot=[{"kind": "editorial_warning", "on_match": "warn"}],
    )
    db.add(round_)
    db.flush()
    db.add(RoundMember(round_id=round_.id, user_id=contributor.id))
    db.commit()

    original = TrackInput(
        spotify_track_id=f"original-{suffix}",
        name="Original",
        artist="The Testers",
    )
    created = create_submission(
        round_.id,
        SubmissionCreate(track=original, note="original note", confirm_warnings=True),
        db,
        contributor,
    )
    assert created["accepted"] is True
    submission_id = uuid.UUID(str(created["id"]))

    replacement = TrackInput(
        spotify_track_id=f"replacement-{suffix}",
        name="Replacement",
        artist="The Testers",
    )
    needs_confirmation = update_submission(
        submission_id,
        SubmissionUpdate(track=replacement),
        db,
        contributor,
    )
    assert needs_confirmation["accepted"] is False
    assert needs_confirmation["requiresWarningConfirmation"] is True
    db.expire_all()
    submission = db.get(Submission, submission_id)
    assert submission is not None
    assert submission.note == "original note"
    assert (
        db.scalar(select(Track.spotify_track_id).where(Track.id == submission.track_id))
        == original.spotify_track_id
    )

    updated = update_submission(
        submission_id,
        SubmissionUpdate(track=replacement, confirm_warnings=True),
        db,
        contributor,
    )
    assert updated["accepted"] is True
    db.expire_all()
    submission = db.get(Submission, submission_id)
    assert submission is not None
    assert submission.note == "original note"
    assert (
        db.scalar(select(Track.spotify_track_id).where(Track.id == submission.track_id))
        == replacement.spotify_track_id
    )
    assert (
        db.scalar(
            select(func.count())
            .select_from(PolicyEvaluation)
            .where(PolicyEvaluation.submission_id == submission_id)
        )
        == 2
    )


def test_open_round_drafts_are_restored_for_their_owner(db: Session) -> None:
    suffix = uuid.uuid4().hex[:12]
    now = datetime.now(UTC)
    contributor = User(
        oidc_issuer="https://issuer.test",
        oidc_subject=f"draft-contributor-{suffix}",
        platform_role=PlatformRole.MEMBER,
    )
    series = Series(
        name=f"Draft series {suffix}",
        slug=f"draft-series-{suffix}",
        timezone="UTC",
        default_policies=[],
    )
    db.add_all((contributor, series))
    db.flush()
    round_ = Round(
        series_id=series.id,
        title="Draft round",
        timezone="UTC",
        submission_limit=3,
        opens_at=now - timedelta(minutes=5),
        closes_at=now + timedelta(minutes=5),
        publish_at=now + timedelta(minutes=10),
        status=RoundStatus.OPEN,
        policy_snapshot=[],
    )
    db.add(round_)
    db.flush()
    db.add(RoundMember(round_id=round_.id, user_id=contributor.id))
    db.commit()

    track = TrackInput(
        spotify_track_id=f"draft-track-{suffix}",
        name="A saved thought",
        artist="The Testers",
        album="The album",
    )
    saved = save_submission_draft(
        round_.id,
        SubmissionDraftUpdate(track=track, note="Come back to this."),
        db,
        contributor,
    )
    assert saved["note"] == "Come back to this."
    assert saved["track"] == track.model_dump()
    assert get_submission_draft(round_.id, db, contributor) == saved


def test_recent_series_repeat_only_considers_the_configured_published_window(db: Session) -> None:
    suffix = uuid.uuid4().hex[:12]
    now = datetime.now(UTC)
    user = User(
        oidc_issuer="https://issuer.test",
        oidc_subject=f"series-policy-{suffix}",
        platform_role=PlatformRole.MEMBER,
    )
    series = Series(
        name=f"Policy series {suffix}",
        slug=f"policy-{suffix}",
        timezone="UTC",
        default_policies=[],
    )
    db.add_all((user, series))
    db.flush()
    track = Track(
        spotify_track_id=f"series-track-{suffix}",
        name="A repeated track",
        artist="The Testers",
        spotify_uri=f"spotify:track:{suffix}",
    )
    db.add(track)
    db.flush()
    older = Round(
        series_id=series.id,
        title=f"Older {suffix}",
        timezone="UTC",
        submission_limit=1,
        opens_at=now - timedelta(days=6),
        closes_at=now - timedelta(days=5),
        publish_at=now - timedelta(days=4),
        status=RoundStatus.PUBLISHED,
        published_sequence=1,
        policy_snapshot=[],
    )
    latest = Round(
        series_id=series.id,
        title=f"Latest {suffix}",
        timezone="UTC",
        submission_limit=1,
        opens_at=now - timedelta(days=3),
        closes_at=now - timedelta(days=2),
        publish_at=now - timedelta(days=1),
        status=RoundStatus.PUBLISHED,
        published_sequence=2,
        policy_snapshot=[],
    )
    current = Round(
        series_id=series.id,
        title=f"Current {suffix}",
        timezone="UTC",
        submission_limit=1,
        opens_at=now - timedelta(hours=1),
        closes_at=now + timedelta(hours=1),
        publish_at=now + timedelta(hours=2),
        status=RoundStatus.OPEN,
        policy_snapshot=[],
    )
    db.add_all((older, latest, current))
    db.flush()
    db.add(Submission(round_id=older.id, contributor_id=user.id, track_id=track.id))
    db.commit()

    policy = {"kind": "no_recent_series_repeat", "lookback_rounds": 1}
    assert evaluate_submission(db, current, track.id, [policy]) == []

    db.add(
        Submission(
            round_id=latest.id,
            contributor_id=user.id,
            track_id=track.id,
            status=SubmissionStatus.ACCEPTED,
        )
    )
    db.commit()
    results = evaluate_submission(db, current, track.id, [policy])
    assert len(results) == 1
    assert results[0].decision is EvaluationDecision.REJECT
    assert results[0].result["lookbackRounds"] == 1


def test_concurrent_submissions_cannot_exceed_a_member_limit() -> None:
    suffix = uuid.uuid4().hex[:12]
    now = datetime.now(UTC)
    with get_session_factory()() as db:
        contributor = User(
            oidc_issuer="https://issuer.test",
            oidc_subject=f"concurrent-{suffix}",
            platform_role=PlatformRole.MEMBER,
        )
        series = Series(
            name=f"Concurrent series {suffix}",
            slug=f"concurrent-{suffix}",
            timezone="UTC",
            default_policies=[],
        )
        db.add_all((contributor, series))
        db.flush()
        round_ = Round(
            series_id=series.id,
            title=f"Concurrent round {suffix}",
            timezone="UTC",
            submission_limit=1,
            opens_at=now - timedelta(minutes=5),
            closes_at=now + timedelta(minutes=5),
            publish_at=now + timedelta(minutes=10),
            status=RoundStatus.OPEN,
            policy_snapshot=[],
        )
        db.add(round_)
        db.flush()
        db.add(RoundMember(round_id=round_.id, user_id=contributor.id))
        db.commit()
        round_id, user_id = round_.id, contributor.id

    def submit(index: int) -> int:
        with get_session_factory()() as worker_db:
            worker_user = worker_db.get(User, user_id)
            assert worker_user is not None
            try:
                result = create_submission(
                    round_id,
                    SubmissionCreate(
                        track=TrackInput(
                            spotify_track_id=f"concurrent-track-{suffix}-{index}",
                            name=f"Concurrent {index}",
                            artist="The Testers",
                            spotify_uri=f"spotify:track:{suffix}{index}",
                        )
                    ),
                    worker_db,
                    worker_user,
                )
                return 201 if result["accepted"] else 409
            except HTTPException as error:
                return error.status_code

    task_app.open()
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(submit, range(2)))
    finally:
        task_app.close()
    assert sorted(outcomes) == [201, 409]
    with get_session_factory()() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(Submission)
                .where(
                    Submission.round_id == round_id,
                    Submission.status == SubmissionStatus.ACCEPTED,
                )
            )
            == 1
        )
