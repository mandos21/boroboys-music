"""Contributor-visible round and submission endpoints."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert

from app.api.deps import DbSession, get_current_user, require_csrf
from app.core.config import get_settings
from app.db.models import (
    EvaluationDecision,
    EvidenceVisibility,
    ExternalAccount,
    ExternalProvider,
    ListeningEvidence,
    PlatformRole,
    PolicyEvaluation,
    Publication,
    Round,
    RoundMember,
    RoundStatus,
    SeriesAdmin,
    Submission,
    SubmissionDraft,
    SubmissionStatus,
    Track,
    User,
)
from app.services import lastfm, spotify
from app.services.lifecycle import reconcile_round_status
from app.services.policies import evaluate_submission
from app.services.publications import get_spotify_access_token
from app.tasks import defer_evidence_refresh

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


class SubmissionDraftUpdate(BaseModel):
    track: TrackInput | None = None
    note: str | None = Field(default=None, max_length=4000)


class TrackEvaluationRequest(BaseModel):
    track: TrackInput


@router.get("")
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
            "id": str(round_.id),
            "seriesId": str(round_.series_id),
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
    round_, membership = _viewer_round(db, round_id, user)
    if reconcile_round_status(round_):
        db.commit()
    limit = (
        membership.submission_limit_override
        if membership.submission_limit_override is not None
        else round_.submission_limit
    ) if membership is not None else round_.submission_limit
    playlist_id = db.scalar(
        select(Publication.spotify_playlist_id).where(
            Publication.round_id == round_.id,
            Publication.spotify_playlist_id.is_not(None),
        )
    )
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
    return {
        "id": str(round_.id),
        "seriesId": str(round_.series_id),
        "title": round_.title,
        "status": round_.status.value,
        "opensAt": round_.opens_at.isoformat(),
        "closesAt": round_.closes_at.isoformat(),
        "publishAt": round_.publish_at.isoformat(),
        "submissionLimit": limit,
        "spotifyPlaylistUrl": f"https://open.spotify.com/playlist/{playlist_id}" if playlist_id else None,
        "prompt": round_.prompt,
        "submittedCount": submitted_count,
        "contributorCount": contributor_count,
    }


@router.get("/{round_id}/draft")
def get_submission_draft(
    round_id: uuid.UUID,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, object]:
    _member_round(db, round_id, user.id)
    draft = db.scalar(
        select(SubmissionDraft).where(SubmissionDraft.round_id == round_id, SubmissionDraft.user_id == user.id)
    )
    return {"track": draft.track if draft else None, "note": draft.note if draft else None}


@router.put("/{round_id}/draft", dependencies=[Depends(require_csrf)])
def save_submission_draft(
    round_id: uuid.UUID,
    payload: SubmissionDraftUpdate,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, object]:
    round_, _ = _member_round(db, round_id, user.id)
    _require_open_round(round_)
    draft = db.scalar(
        select(SubmissionDraft).where(SubmissionDraft.round_id == round_id, SubmissionDraft.user_id == user.id)
    )
    if draft is None:
        draft = SubmissionDraft(round_id=round_id, user_id=user.id)
        db.add(draft)
    draft.track = payload.track.model_dump() if payload.track else None
    draft.note = payload.note
    db.commit()
    return {"track": draft.track, "note": draft.note}


@router.get("/{round_id}/listening-suggestions")
def get_listening_suggestions(
    round_id: uuid.UUID,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> list[dict[str, str]]:
    _member_round(db, round_id, user.id)
    account = db.scalar(
        select(ExternalAccount).where(
            ExternalAccount.user_id == user.id,
            ExternalAccount.provider == ExternalProvider.LASTFM,
            ExternalAccount.is_active.is_(True),
        )
    )
    if account is None:
        return []
    try:
        return lastfm.monthly_top_tracks(get_settings(), account.provider_subject)
    except (httpx.HTTPError, lastfm.LastfmError, ValueError):
        return []


@router.get("/{round_id}/submissions")
def list_round_submissions(
    round_id: uuid.UUID,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> list[dict[str, object]]:
    """Show accepted entries to round members and a user's withdrawn entries to them.

    The active membership check is intentional: a person removed from a private
    round must not retain a general read capability merely because their old
    submission remains attributable in publication history.
    """
    _, membership = _viewer_round(db, round_id, user)
    visible_statuses = Submission.status == SubmissionStatus.ACCEPTED
    if membership is not None:
        visible_statuses = visible_statuses | (Submission.contributor_id == user.id)
    spotify_profile_image = (
        select(ExternalAccount.profile_image_url)
        .where(
            ExternalAccount.user_id == Submission.contributor_id,
            ExternalAccount.provider == ExternalProvider.SPOTIFY,
            ExternalAccount.is_active.is_(True),
        )
        .order_by(ExternalAccount.created_at)
        .limit(1)
        .scalar_subquery()
    )
    rows = db.execute(
        select(Submission, Track, User, spotify_profile_image)
        .join(Track, Track.id == Submission.track_id)
        .join(User, User.id == Submission.contributor_id)
        .where(
            Submission.round_id == round_id,
            visible_statuses,
        )
        .order_by(Submission.created_at.asc())
    )
    return [
        {
            "id": str(submission.id),
            "status": submission.status.value,
            "note": submission.note,
            "createdAt": submission.created_at.isoformat(),
            "updatedAt": submission.updated_at.isoformat(),
            "withdrawnAt": submission.withdrawn_at.isoformat() if submission.withdrawn_at else None,
            "isMine": submission.contributor_id == user.id,
            "contributor": {
                "id": str(contributor.id),
                "displayName": contributor.display_name
                or contributor.email
                or "Unknown listener",
                "spotifyProfileImageUrl": profile_image_url,
            },
            "track": _track_payload(track),
        }
        for submission, track, contributor, profile_image_url in rows
    ]


@router.get("/{round_id}/track-search")
def search_tracks(
    round_id: uuid.UUID,
    query: Annotated[str, Query(min_length=2, max_length=200)],
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> list[dict[str, object]]:
    _member_round(db, round_id, user.id)
    account = db.scalar(
        select(ExternalAccount).where(
            ExternalAccount.user_id == user.id,
            ExternalAccount.provider == ExternalProvider.SPOTIFY,
            ExternalAccount.is_active.is_(True),
        )
    )
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Spotify account is not linked"
        )
    try:
        access_token = get_spotify_access_token(db, account.id)
        # A refresh changes durable credentials.  Checkpoint it before the
        # unrelated remote search so a search failure cannot discard it.
        db.commit()
        matches = spotify.search_tracks(access_token, query)
    except (httpx.HTTPError, spotify.SpotifyError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="Spotify search failed"
        ) from None
    return [
        {
            "spotifyTrackId": item.get("id"),
            "name": item.get("name"),
            "artist": ", ".join(
                artist.get("name", "")
                for artist in item.get("artists", [])
                if isinstance(artist, dict)
            ),
            "album": item.get("album", {}).get("name")
            if isinstance(item.get("album"), dict)
            else None,
            "spotifyUri": item.get("uri"),
            "artworkUrl": (item.get("album", {}).get("images") or [{}])[0].get("url")
            if isinstance(item.get("album"), dict)
            else None,
            "providerMetadata": {
                "explicit": item.get("explicit", False),
                "isPlayable": item.get("is_playable", True),
            },
        }
        for item in matches
        if isinstance(item.get("id"), str) and isinstance(item.get("name"), str)
    ]


@router.get("/{round_id}/tracks/{track_id}/evidence")
def get_evidence(
    round_id: uuid.UUID,
    track_id: uuid.UUID,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, object]:
    round_ = db.get(Round, round_id)
    if round_ is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="round not found")
    is_member = (
        db.scalar(
            select(RoundMember.id).where(
                RoundMember.round_id == round_id,
                RoundMember.user_id == user.id,
                RoundMember.removed_at.is_(None),
            )
        )
        is not None
    )
    is_series_admin = (
        user.platform_role is PlatformRole.ADMIN
        or db.scalar(
            select(SeriesAdmin.id).where(
                SeriesAdmin.series_id == round_.series_id,
                SeriesAdmin.user_id == user.id,
            )
        )
        is not None
    )
    if not is_member and not is_series_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="round access required")
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
        if account.user_id == user.id:
            pass
        elif account.evidence_visibility is EvidenceVisibility.ROUND_MEMBERS and is_member:
            pass
        elif account.evidence_visibility is EvidenceVisibility.SERIES_ADMINS and is_series_admin:
            pass
        else:
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
    "/{round_id}/evaluate-track",
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
    track = _find_or_create_track(db, payload.track)
    decisions = evaluate_submission(db, round_, track.id, round_.policy_snapshot)
    db.commit()
    defer_evidence_refresh(str(round_.id), str(track.id))
    rejected = any(item.decision is EvaluationDecision.REJECT for item in decisions)
    warnings = any(item.decision is EvaluationDecision.WARN for item in decisions)
    return {
        "trackId": str(track.id),
        "canSubmit": active_count < limit and not rejected,
        "limitRemaining": max(0, limit - active_count),
        "requiresWarningConfirmation": warnings,
        "policyResults": [_policy_payload(item) for item in decisions],
    }


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
    _require_open_round(round_)
    limit = _submission_limit(round_, membership)
    active_count = _active_submission_count(db, round_.id, user.id)
    if active_count >= limit:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="submission limit reached")

    track = _find_or_create_track(db, payload.track)
    decisions = evaluate_submission(db, round_, track.id, round_.policy_snapshot)
    if any(item.decision is EvaluationDecision.REJECT for item in decisions):
        return {
            "accepted": False,
            "requiresWarningConfirmation": False,
            "policyResults": [_policy_payload(item) for item in decisions],
        }
    if any(item.decision is EvaluationDecision.WARN for item in decisions) and not payload.confirm_warnings:
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
    return {
        "accepted": True,
        "id": str(submission.id),
        "policyResults": [_policy_payload(item) for item in decisions],
    }


@router.patch(
    "/submissions/{submission_id}",
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
    round_, _ = _member_round(db, submission.round_id, user.id, lock_round=True)
    _require_open_round(round_)

    decisions = []
    if payload.track is not None:
        track = _find_or_create_track(db, payload.track)
        decisions = evaluate_submission(db, round_, track.id, round_.policy_snapshot)
        if any(item.decision is EvaluationDecision.REJECT for item in decisions):
            return {
                "accepted": False,
                "requiresWarningConfirmation": False,
                "policyResults": [_policy_payload(item) for item in decisions],
            }
        if any(item.decision is EvaluationDecision.WARN for item in decisions) and not payload.confirm_warnings:
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


def _viewer_round(
    db: DbSession, round_id: uuid.UUID, user: User
) -> tuple[Round, RoundMember | None]:
    """Authorize a contributor or the series' normal administrator.

    A series administrator has management access without becoming a contributor.
    That is not a separate round-administrator role, and it does not allow the
    administrator to submit or inspect a contributor's withdrawn entry.
    """
    round_ = db.get(Round, round_id)
    if round_ is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="round not found")
    membership = db.scalar(
        select(RoundMember).where(
            RoundMember.round_id == round_id,
            RoundMember.user_id == user.id,
            RoundMember.removed_at.is_(None),
        )
    )
    if membership is not None:
        return round_, membership
    is_admin = user.platform_role is PlatformRole.ADMIN or (
        db.scalar(
            select(SeriesAdmin.id).where(
                SeriesAdmin.series_id == round_.series_id,
                SeriesAdmin.user_id == user.id,
            )
        )
        is not None
    )
    if not is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="round access required")
    return round_, None


def _require_open_round(round_: Round) -> None:
    now = datetime.now(UTC)
    if round_.status is not RoundStatus.OPEN or not (round_.opens_at <= now < round_.closes_at):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="round is not accepting submissions"
        )


def _submission_limit(round_: Round, membership: RoundMember) -> int:
    return (
        membership.submission_limit_override
        if membership.submission_limit_override is not None
        else round_.submission_limit
    )


def _active_submission_count(db: DbSession, round_id: uuid.UUID, user_id: uuid.UUID) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(Submission)
            .where(
                Submission.round_id == round_id,
                Submission.contributor_id == user_id,
                Submission.status == SubmissionStatus.ACCEPTED,
            )
        )
        or 0
    )


def _find_or_create_track(db: DbSession, input_track: TrackInput) -> Track:
    track = db.scalar(select(Track).where(Track.spotify_track_id == input_track.spotify_track_id))
    if track is not None:
        if track.artwork_url is None and input_track.artwork_url is not None:
            track.artwork_url = input_track.artwork_url
        if track.album is None and input_track.album is not None:
            track.album = input_track.album
        if track.spotify_uri is None and input_track.spotify_uri is not None:
            track.spotify_uri = input_track.spotify_uri
        return track
    # Tracks are shared across overlapping rounds.  PostgreSQL resolves the
    # first-insert race without turning a normal simultaneous evaluation into
    # an IntegrityError/500.
    result = db.execute(
        insert(Track)
        .values(**input_track.model_dump())
        .on_conflict_do_nothing(index_elements=[Track.spotify_track_id])
        .returning(Track.id)
    )
    track_id = result.scalar_one_or_none()
    if track_id is not None:
        track = db.get(Track, track_id)
    else:
        track = db.scalar(select(Track).where(Track.spotify_track_id == input_track.spotify_track_id))
    if track is None:  # defensive: only possible with an unexpected transaction failure
        raise RuntimeError("track insert did not return a track")
    return track


def _policy_payload(result: Any) -> dict[str, object]:
    return {
        "kind": result.kind,
        "version": result.version,
        "decision": result.decision.value,
        "message": result.message,
        "result": result.result,
    }


def _track_payload(track: Track) -> dict[str, object]:
    return {
        "spotifyTrackId": track.spotify_track_id,
        "name": track.name,
        "artist": track.artist,
        "album": track.album,
        "spotifyUri": track.spotify_uri,
        "artworkUrl": track.artwork_url,
    }
