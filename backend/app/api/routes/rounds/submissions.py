"""Creating, replacing, and withdrawing a contributor's submission."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import delete

from app.api.deps import DbSession, get_current_user, require_csrf
from app.api.routes.rounds._common import (
    TrackInput,
    _active_submission_count,
    _canonical_track_input,
    _find_or_create_track,
    _member_round,
    _policy_payload,
    _require_open_round,
    _submission_limit,
    router,
)
from app.api.schemas import (
    SubmissionResultResponse,
    TrackEvaluationResponse,
)
from app.db.models import (
    EvaluationDecision,
    PolicyEvaluation,
    RoundStatus,
    Submission,
    SubmissionDraft,
    SubmissionStatus,
    User,
)
from app.services.policies import evaluate_submission
from app.tasks import defer_evidence_refresh, defer_track_genre_enrichment


class SubmissionCreate(BaseModel):
    track: TrackInput
    note: str | None = Field(default=None, max_length=4000)
    confirm_warnings: bool = False


class SubmissionUpdate(BaseModel):
    """A contributor-owned change while the round is still accepting entries.

    A track change is deliberately evaluated exactly like a new submission.  The
    existing policy-evaluation rows are retained as an audit trail instead of
    overwriting the decision that was made for the previous track.
    """

    track: TrackInput | None = None
    note: str | None = Field(default=None, max_length=4000)
    confirm_warnings: bool = False


class TrackEvaluationRequest(BaseModel):
    track: TrackInput
    replacing_submission_id: uuid.UUID | None = None


@router.post(
    "/{round_id}/evaluate-track",
    response_model=TrackEvaluationResponse,
    dependencies=[Depends(require_csrf)],
)
def evaluate_track(
    round_id: uuid.UUID,
    payload: TrackEvaluationRequest,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, object]:
    """Evaluate a candidate before a contributor confirms a submission."""
    round_, membership = _member_round(db, round_id, user.id)
    _require_open_round(round_)
    limit = _submission_limit(round_, membership)
    active_count = _active_submission_count(db, round_.id, user.id)
    is_replacement = False
    if payload.replacing_submission_id is not None:
        replacing = db.get(Submission, payload.replacing_submission_id)
        is_replacement = bool(
            replacing
            and replacing.round_id == round_.id
            and replacing.contributor_id == user.id
            and replacing.status is SubmissionStatus.ACCEPTED
        )
        if not is_replacement:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="submission not found"
            )
    track = _find_or_create_track(db, _canonical_track_input(db, user, payload.track))
    decisions = evaluate_submission(db, round_, track.id, round_.policy_snapshot)
    db.commit()
    defer_evidence_refresh(str(round_.id), str(track.id))
    defer_track_genre_enrichment(str(track.id))
    rejected = any(item.decision is EvaluationDecision.REJECT for item in decisions)
    warnings = any(item.decision is EvaluationDecision.WARN for item in decisions)
    return {
        "trackId": str(track.id),
        "canSubmit": (active_count < limit or is_replacement) and not rejected,
        "limitRemaining": max(0, limit - active_count),
        "requiresWarningConfirmation": warnings,
        "policyResults": [_policy_payload(item) for item in decisions],
    }


@router.post(
    "/{round_id}/submissions",
    status_code=status.HTTP_201_CREATED,
    response_model=SubmissionResultResponse,
    dependencies=[Depends(require_csrf)],
)
def create_submission(
    round_id: uuid.UUID,
    payload: SubmissionCreate,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, object]:
    # Authorize before the provider request, then lock and check again after it.
    # We must not hold a row lock across remote I/O.
    initial_round, _ = _member_round(db, round_id, user.id)
    _require_open_round(initial_round)
    canonical_track = _canonical_track_input(db, user, payload.track)
    round_, membership = _member_round(db, round_id, user.id, lock_round=True)
    _require_open_round(round_)
    limit = _submission_limit(round_, membership)
    active_count = _active_submission_count(db, round_.id, user.id)
    if active_count >= limit:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="submission limit reached")

    track = _find_or_create_track(db, canonical_track)
    decisions = evaluate_submission(db, round_, track.id, round_.policy_snapshot)
    if any(item.decision is EvaluationDecision.REJECT for item in decisions):
        return {
            "accepted": False,
            "requiresWarningConfirmation": False,
            "policyResults": [_policy_payload(item) for item in decisions],
        }
    if (
        any(item.decision is EvaluationDecision.WARN for item in decisions)
        and not payload.confirm_warnings
    ):
        return {
            "accepted": False,
            "requiresWarningConfirmation": True,
            "policyResults": [_policy_payload(item) for item in decisions],
        }

    submission = Submission(
        round_id=round_.id, contributor_id=user.id, track_id=track.id, note=payload.note
    )
    db.add(submission)
    db.flush()
    # Submitting again is the clearest possible way of saying "I changed my
    # mind"; making people untoggle the declaration by hand would leave their
    # reminders silenced for the capacity they still have.
    membership.declined_further_submissions_at = None
    db.add_all(
        PolicyEvaluation(
            round_id=round_.id,
            submission_id=submission.id,
            track_id=track.id,
            policy_kind=item.kind,
            policy_version=item.version,
            decision=item.decision,
            message=item.message,
            result=item.result,
        )
        for item in decisions
    )
    db.execute(
        delete(SubmissionDraft).where(
            SubmissionDraft.round_id == round_.id,
            SubmissionDraft.user_id == user.id,
        )
    )
    db.commit()
    defer_evidence_refresh(str(round_.id), str(track.id))
    defer_track_genre_enrichment(str(track.id))
    return {
        "accepted": True,
        "id": str(submission.id),
        "policyResults": [_policy_payload(item) for item in decisions],
    }


@router.patch(
    "/submissions/{submission_id}",
    response_model=SubmissionResultResponse,
    dependencies=[Depends(require_csrf)],
)
def update_submission(
    submission_id: uuid.UUID,
    payload: SubmissionUpdate,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, object]:
    """Update a note or replace a submitted track before the round closes."""
    submission = db.get(Submission, submission_id)
    if submission is None or submission.contributor_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="submission not found")
    if submission.status is not SubmissionStatus.ACCEPTED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="submission is withdrawn")
    initial_round, _ = _member_round(db, submission.round_id, user.id)
    _require_open_round(initial_round)
    canonical_track = (
        _canonical_track_input(db, user, payload.track) if payload.track is not None else None
    )
    round_, _ = _member_round(db, submission.round_id, user.id, lock_round=True)
    _require_open_round(round_)

    decisions = []
    if canonical_track is not None:
        track = _find_or_create_track(db, canonical_track)
        decisions = evaluate_submission(db, round_, track.id, round_.policy_snapshot)
        if any(item.decision is EvaluationDecision.REJECT for item in decisions):
            return {
                "accepted": False,
                "requiresWarningConfirmation": False,
                "policyResults": [_policy_payload(item) for item in decisions],
            }
        if (
            any(item.decision is EvaluationDecision.WARN for item in decisions)
            and not payload.confirm_warnings
        ):
            return {
                "accepted": False,
                "requiresWarningConfirmation": True,
                "policyResults": [_policy_payload(item) for item in decisions],
            }
        submission.track_id = track.id
        db.add_all(
            PolicyEvaluation(
                round_id=round_.id,
                submission_id=submission.id,
                track_id=track.id,
                policy_kind=item.kind,
                policy_version=item.version,
                decision=item.decision,
                message=item.message,
                result=item.result,
            )
            for item in decisions
        )
    if "note" in payload.model_fields_set:
        submission.note = payload.note
    if payload.track is not None:
        db.execute(
            delete(SubmissionDraft).where(
                SubmissionDraft.round_id == round_.id,
                SubmissionDraft.user_id == user.id,
            )
        )
    db.commit()
    if payload.track is not None:
        defer_evidence_refresh(str(round_.id), str(submission.track_id))
        defer_track_genre_enrichment(str(submission.track_id))
    return {
        "accepted": True,
        "id": str(submission.id),
        "policyResults": [_policy_payload(item) for item in decisions],
    }


@router.post(
    "/submissions/{submission_id}/withdraw",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
    dependencies=[Depends(require_csrf)],
)
def withdraw_submission(
    submission_id: uuid.UUID,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> None:
    submission = db.get(Submission, submission_id)
    if submission is None or submission.contributor_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="submission not found")
    round_, _ = _member_round(db, submission.round_id, user.id, lock_round=True)
    if round_.status is not RoundStatus.OPEN or datetime.now(UTC) >= round_.closes_at:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="round is closed")
    submission.status = SubmissionStatus.WITHDRAWN
    submission.withdrawn_at = datetime.now(UTC)
    db.commit()
