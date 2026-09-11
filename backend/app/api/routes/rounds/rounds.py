"""Rounds a contributor can see, and their saved submission draft."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.deps import DbSession, get_current_user, require_csrf
from app.api.payloads import (
    round_artwork_urls_by_round,
    round_timeline,
    stable_pick,
)
from app.api.routes.rounds._common import (
    TrackInput,
    _member_round,
    _require_open_round,
    _viewer_round,
    router,
)
from app.api.schemas import (
    RoundDetailResponse,
    RoundListResponse,
    RoundParticipationResponse,
    SubmissionDraftResponse,
)
from app.db.models import (
    Publication,
    Round,
    RoundMember,
    Submission,
    SubmissionDraft,
    SubmissionStatus,
    Track,
    User,
)
from app.services.authorization import is_series_admin
from app.services.lifecycle import reconcile_round_status


class SubmissionDraftUpdate(BaseModel):
    track: TrackInput | None = None
    note: str | None = Field(default=None, max_length=4000)


@router.get("", response_model=list[RoundListResponse])
def list_my_rounds(
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> list[dict[str, object]]:
    result = db.execute(
        select(Round, RoundMember)
        .join(RoundMember, RoundMember.round_id == Round.id)
        .where(RoundMember.user_id == user.id, RoundMember.removed_at.is_(None))
        .order_by(Round.opens_at.desc())
    )
    rows = list(result)
    if any(reconcile_round_status(round_) for round_, _ in rows):
        db.commit()
    return [
        {
            **round_timeline(round_),
            "seriesId": str(round_.series_id),
            "submissionLimit": (
                member.submission_limit_override
                if member.submission_limit_override is not None
                else round_.submission_limit
            ),
        }
        for round_, member in rows
    ]


@router.get("/{round_id}", response_model=RoundDetailResponse)
def get_round(
    round_id: uuid.UUID,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, object]:
    round_, membership = _viewer_round(db, round_id, user)
    if reconcile_round_status(round_):
        db.commit()
    limit = (
        (
            membership.submission_limit_override
            if membership.submission_limit_override is not None
            else round_.submission_limit
        )
        if membership is not None
        else round_.submission_limit
    )
    playlist_id = db.scalar(
        select(Publication.spotify_playlist_id).where(
            Publication.round_id == round_.id,
            Publication.spotify_playlist_id.is_not(None),
        )
    )
    # A stable choice per round. Re-rolling this on every request made the round
    # header change its backdrop each time the page refetched.
    artwork_urls: list[str] = list(
        db.scalars(
            select(Track.artwork_url)
            .join(Submission, Submission.track_id == Track.id)
            .where(
                Submission.round_id == round_.id,
                Submission.status == SubmissionStatus.ACCEPTED,
                Track.artwork_url.is_not(None),
            )
            .order_by(Submission.created_at, Submission.id)
        )
    )
    background_artwork_url = stable_pick(artwork_urls, round_.id)
    # The same balanced selection the series history uses, so a release recap
    # does not need a second implementation of it in the browser.
    balanced_artwork = round_artwork_urls_by_round(db, [round_.id]).get(round_.id, [])
    submitted_count = int(
        db.scalar(
            select(func.count(func.distinct(Submission.contributor_id))).where(
                Submission.round_id == round_.id,
                Submission.status == SubmissionStatus.ACCEPTED,
            )
        )
        or 0
    )
    contributor_count = int(
        db.scalar(
            select(func.count())
            .select_from(RoundMember)
            .where(RoundMember.round_id == round_.id, RoundMember.removed_at.is_(None))
        )
        or 0
    )
    can_manage = is_series_admin(db, round_.series_id, user)
    return {
        **round_timeline(round_),
        "seriesId": str(round_.series_id),
        "submissionLimit": limit,
        "spotifyPlaylistUrl": (
            f"https://open.spotify.com/playlist/{playlist_id}" if playlist_id else None
        ),
        "submittedCount": submitted_count,
        "contributorCount": contributor_count,
        "canManage": can_manage,
        "isMember": membership is not None,
        "backgroundArtworkUrl": background_artwork_url,
        "artworkUrls": balanced_artwork,
        "declinedFurtherSubmissions": (
            membership is not None and membership.declined_further_submissions_at is not None
        ),
    }


class RoundParticipationUpdate(BaseModel):
    declined_further_submissions: bool


@router.patch(
    "/{round_id}/participation",
    response_model=RoundParticipationResponse,
    dependencies=[Depends(require_csrf)],
)
def update_round_participation(
    round_id: uuid.UUID,
    payload: RoundParticipationUpdate,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, object]:
    """Let a member declare they're deliberately done submitting for this round.

    Distinct from having hit the submission limit - this is what keeps deadline
    reminders from nagging someone who has already decided to sit a round out.
    """
    round_, membership = _member_round(db, round_id, user.id)
    if reconcile_round_status(round_):
        db.commit()
    if payload.declined_further_submissions:
        membership.declined_further_submissions_at = (
            membership.declined_further_submissions_at or datetime.now(UTC)
        )
    else:
        membership.declined_further_submissions_at = None
    db.commit()
    return {"declinedFurtherSubmissions": membership.declined_further_submissions_at is not None}


@router.get("/{round_id}/draft", response_model=SubmissionDraftResponse)
def get_submission_draft(
    round_id: uuid.UUID,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, object]:
    _member_round(db, round_id, user.id)
    draft = db.scalar(
        select(SubmissionDraft).where(
            SubmissionDraft.round_id == round_id, SubmissionDraft.user_id == user.id
        )
    )
    return {"track": draft.track if draft else None, "note": draft.note if draft else None}


@router.put(
    "/{round_id}/draft",
    response_model=SubmissionDraftResponse,
    dependencies=[Depends(require_csrf)],
)
def save_submission_draft(
    round_id: uuid.UUID,
    payload: SubmissionDraftUpdate,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, object]:
    round_, _ = _member_round(db, round_id, user.id)
    _require_open_round(round_)
    draft = db.scalar(
        select(SubmissionDraft).where(
            SubmissionDraft.round_id == round_id, SubmissionDraft.user_id == user.id
        )
    )
    if draft is None:
        draft = SubmissionDraft(round_id=round_id, user_id=user.id)
        db.add(draft)
    draft.track = payload.track.model_dump() if payload.track else None
    draft.note = payload.note
    db.commit()
    return {"track": draft.track, "note": draft.note}
