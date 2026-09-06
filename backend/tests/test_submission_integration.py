"""PostgreSQL-backed acceptance coverage for the contributor submission flow."""

from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from app.api.routes.rounds import (
    SubmissionCreate,
    TrackEvaluationRequest,
    TrackInput,
    create_submission,
    evaluate_track,
)
from app.db.models import (
    EvaluationDecision,
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
from app.services.policies import evaluate_submission
from app.tasks import app as task_app


@pytest.fixture
def opened_task_app() -> None:
    task_app.open()
    try:
        yield
    finally:
        task_app.close()


def test_warning_requires_confirmation_and_persists_an_audit_record(opened_task_app: None) -> None:
    """A real transaction cannot turn a warning into an accepted submission by accident."""
    suffix = uuid.uuid4().hex[:12]
    now = datetime.now(UTC)
    with get_session_factory()() as db:
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
        preflight = evaluate_track(
            round_.id, TrackEvaluationRequest(track=track), db, contributor
        )
        assert preflight["canSubmit"] is True
        assert preflight["requiresWarningConfirmation"] is True
        assert preflight["limitRemaining"] == 1

        unconfirmed = create_submission(
            round_.id, SubmissionCreate(track=track), db, contributor
        )
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


def test_recent_series_repeat_only_considers_the_configured_published_window() -> None:
    suffix = uuid.uuid4().hex[:12]
    now = datetime.now(UTC)
    with get_session_factory()() as db:
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
