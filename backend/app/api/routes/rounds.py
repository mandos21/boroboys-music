"""Contributor-visible round and submission endpoints."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.deps import DbSession, get_current_user, require_csrf
from app.db.models import (
    EvaluationDecision,
    EvidenceVisibility,
    ExternalAccount,
    ExternalProvider,
    ListeningEvidence,
    PolicyEvaluation,
    Round,
    RoundMember,
    RoundStatus,
    Submission,
    SubmissionStatus,
    Track,
    User,
)
from app.services.policies import evaluate_submission
from app.tasks import refresh_evidence

router = APIRouter(prefix="/rounds", tags=["rounds"])


class TrackInput(BaseModel):
    spotify_track_id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=500)
    artist: str = Field(min_length=1, max_length=500)
    album: str | None = Field(default=None, max_length=500)
    spotify_uri: str | None = Field(default=None, max_length=128)
    artwork_url: str | None = Field(default=None, max_length=1000)
    provider_metadata: dict[str, Any] = Field(default_factory=dict)


class SubmissionCreate(BaseModel):
    track: TrackInput
    note: str | None = Field(default=None, max_length=4000)


@router.get("")
def list_my_rounds(
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> list[dict[str, object]]:
    rows = db.execute(
        select(Round, RoundMember)
        .join(RoundMember, RoundMember.round_id == Round.id)
        .where(RoundMember.user_id == user.id, RoundMember.removed_at.is_(None))
        .order_by(Round.opens_at.desc())
    )
    return [
        {
            "id": str(round_.id),
            "title": round_.title,
            "status": round_.status.value,
            "opensAt": round_.opens_at.isoformat(),
            "closesAt": round_.closes_at.isoformat(),
            "publishAt": round_.publish_at.isoformat(),
            "submissionLimit": (
                member.submission_limit_override
                if member.submission_limit_override is not None
                else round_.submission_limit
            ),
        }
        for round_, member in rows
    ]


@router.get("/{round_id}")
def get_round(
    round_id: uuid.UUID,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, object]:
    round_, membership = _member_round(db, round_id, user.id)
    limit = (
        membership.submission_limit_override
        if membership.submission_limit_override is not None
        else round_.submission_limit
    )
    return {
        "id": str(round_.id),
        "title": round_.title,
        "status": round_.status.value,
        "opensAt": round_.opens_at.isoformat(),
        "closesAt": round_.closes_at.isoformat(),
        "publishAt": round_.publish_at.isoformat(),
        "submissionLimit": limit,
    }


@router.get("/{round_id}/tracks/{track_id}/evidence")
def get_evidence(
    round_id: uuid.UUID,
    track_id: uuid.UUID,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, object]:
    round_, _ = _member_round(db, round_id, user.id)
    rows = list(
        db.execute(
            select(ExternalAccount, ListeningEvidence)
            .join(ListeningEvidence, ListeningEvidence.external_account_id == ExternalAccount.id)
            .join(RoundMember, RoundMember.user_id == ExternalAccount.user_id)
            .where(
                RoundMember.round_id == round_.id,
                RoundMember.removed_at.is_(None),
                ExternalAccount.provider == ExternalProvider.LASTFM,
                ListeningEvidence.track_id == track_id,
            )
        )
    )
    evidence = []
    for account, item in rows:
        if (
            account.user_id != user.id
            and account.evidence_visibility is not EvidenceVisibility.ROUND_MEMBERS
        ):
            continue
        evidence.append(
            {
                "accountId": str(account.id),
                "displayName": account.display_name,
                "playcount": item.playcount,
                "fetchedAt": item.fetched_at.isoformat(),
                "refreshAfter": item.refresh_after.isoformat() if item.refresh_after else None,
                "status": item.response_status,
            }
        )
    return {"roundId": str(round_.id), "trackId": str(track_id), "evidence": evidence}


@router.post(
    "/{round_id}/submissions",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
def create_submission(
    round_id: uuid.UUID,
    payload: SubmissionCreate,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, object]:
    round_, membership = _member_round(db, round_id, user.id, lock_round=True)
    now = datetime.now(UTC)
    if round_.status is not RoundStatus.OPEN or not (round_.opens_at <= now < round_.closes_at):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="round is not accepting submissions"
        )
    limit = (
        membership.submission_limit_override
        if membership.submission_limit_override is not None
        else round_.submission_limit
    )
    active_count = db.scalar(
        select(func.count())
        .select_from(Submission)
        .where(
            Submission.round_id == round_.id,
            Submission.contributor_id == user.id,
            Submission.status == SubmissionStatus.ACCEPTED,
        )
    )
    if active_count is not None and active_count >= limit:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="submission limit reached")

    track = db.scalar(select(Track).where(Track.spotify_track_id == payload.track.spotify_track_id))
    if track is None:
        track = Track(**payload.track.model_dump())
        db.add(track)
        db.flush()
    decisions = evaluate_submission(db, round_, track.id, round_.policy_snapshot)
    if any(item.decision is EvaluationDecision.REJECT for item in decisions):
        return {
            "accepted": False,
            "policyResults": [_policy_payload(item) for item in decisions],
        }

    submission = Submission(
        round_id=round_.id, contributor_id=user.id, track_id=track.id, note=payload.note
    )
    db.add(submission)
    db.flush()
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
    db.commit()
    refresh_evidence.defer(str(round_.id), str(track.id))
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


def _member_round(
    db: DbSession, round_id: uuid.UUID, user_id: uuid.UUID, lock_round: bool = False
) -> tuple[Round, RoundMember]:
    query = select(Round).where(Round.id == round_id)
    if lock_round:
        query = query.with_for_update()
    round_ = db.scalar(query)
    if round_ is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="round not found")
    membership = db.scalar(
        select(RoundMember).where(
            RoundMember.round_id == round_id,
            RoundMember.user_id == user_id,
            RoundMember.removed_at.is_(None),
        )
    )
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="round membership required"
        )
    return round_, membership


def _policy_payload(result: Any) -> dict[str, object]:
    return {
        "kind": result.kind,
        "version": result.version,
        "decision": result.decision.value,
        "message": result.message,
        "result": result.result,
    }
