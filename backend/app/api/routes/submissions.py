from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api import deps
from app.db import crud, models
from app.core.dates import normalize_month
from app.schemas import (
    SubmissionCreate,
    SubmissionLimitResponse,
    SubmissionListResponse,
    SubmissionRead,
    SubmissionUpdate,
)
router = APIRouter(prefix="/submissions")


@router.get("", response_model=SubmissionListResponse)
def list_submissions(
    month: Optional[datetime] = None,
    db: Session = Depends(deps.get_db),
    current_user: models.User = Depends(deps.require_user),
) -> SubmissionListResponse:
    month_filter = normalize_month(month) if month else None

    statement = select(models.Submission).order_by(models.Submission.submission_month.desc())
    if month_filter:
        statement = statement.where(models.Submission.submission_month == month_filter)

    if current_user.role != "admin":
        statement = statement.where(models.Submission.user_id == current_user.id)

    submissions = db.scalars(statement).unique().all()
    return SubmissionListResponse(
        items=[SubmissionRead.from_orm(submission) for submission in submissions]
    )


@router.get("/limit/current", response_model=SubmissionLimitResponse)
def get_current_limit(
    month: Optional[datetime] = None,
    db: Session = Depends(deps.get_db),
    current_user: models.User = Depends(deps.require_user),
) -> SubmissionLimitResponse:
    crud.ensure_multi_submission_schema(db)
    current = month or datetime.now(timezone.utc)
    target_month = normalize_month(current)
    settings = crud.get_or_create_month_settings(db, target_month, default_submission_limit=3)
    playlist = crud.get_playlist_by_month(db, target_month)
    used = crud.count_user_submissions_for_month(db, target_month, current_user.id)
    limit_value = settings.submission_limit
    remaining = None if limit_value is None else max(limit_value - used, 0)
    is_locked = bool(playlist and playlist.finalized_by is not None)
    db.commit()
    return SubmissionLimitResponse(
        submission_limit=limit_value,
        used=used,
        remaining=remaining,
        is_locked=is_locked,
    )


@router.post("", response_model=SubmissionRead, status_code=status.HTTP_201_CREATED)
def create_submission(
    payload: SubmissionCreate,
    db: Session = Depends(deps.get_db),
    current_user: models.User = Depends(deps.require_user),
) -> SubmissionRead:
    crud.ensure_multi_submission_schema(db)
    submission_month = normalize_month(payload.submission_month)
    playlist = crud.get_playlist_by_month(db, submission_month)
    if playlist is not None and playlist.finalized_by is not None and current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Submissions are closed for this month.")

    existing_submission = crud.get_user_submission(db, user_id=current_user.id, month=submission_month)
    if existing_submission and existing_submission.is_locked and current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Your submission is locked for this month.")

    settings = crud.get_or_create_month_settings(db, submission_month, default_submission_limit=3)
    if settings.submission_limit is not None and current_user.role != "admin":
        user_submission_count = crud.count_user_submissions_for_month(
            db, submission_month, current_user.id
        )
        if user_submission_count >= settings.submission_limit:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="You've reached your submission limit for this month.",
            )

    track_data = payload.track
    track = crud.upsert_track(
        db,
        spotify_track_id=track_data.spotify_track_id,
        name=track_data.name,
        artist=track_data.artist,
        album=track_data.album,
        duration_ms=track_data.duration_ms,
        release_date=track_data.release_date,
        spotify_url=track_data.spotify_url,
        artwork_url=track_data.artwork_url,
        genres={"items": track_data.genres} if track_data.genres else None,
        lastfm_tags={"tags": track_data.lastfm_tags} if track_data.lastfm_tags else None,
    )
    db.flush()

    submission = crud.create_submission(
        db,
        user=current_user,
        track=track,
        submission_month=submission_month,
        notes=payload.notes,
    )
    db.commit()
    db.refresh(submission)
    return SubmissionRead.from_orm(submission)


@router.patch("/{submission_id}", response_model=SubmissionRead)
def update_submission(
    submission_id: int,
    payload: SubmissionUpdate,
    db: Session = Depends(deps.get_db),
    current_user: models.User = Depends(deps.require_user),
) -> SubmissionRead:
    submission = db.get(models.Submission, submission_id)
    if not submission:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found")

    if current_user.role != "admin" and submission.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    if submission.is_locked and current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Submission locked")

    if payload.track is not None:
        track_data = payload.track
        track = crud.upsert_track(
            db,
            spotify_track_id=track_data.spotify_track_id,
            name=track_data.name,
            artist=track_data.artist,
            album=track_data.album,
            duration_ms=track_data.duration_ms,
            release_date=track_data.release_date,
            spotify_url=track_data.spotify_url,
            artwork_url=track_data.artwork_url,
            genres={"items": track_data.genres} if track_data.genres else None,
            lastfm_tags={"tags": track_data.lastfm_tags} if track_data.lastfm_tags else None,
        )
        db.flush()
        submission.track_id = track.id

    if payload.notes is not None:
        submission.notes = payload.notes
    if payload.submission_month is not None:
        submission.submission_month = normalize_month(payload.submission_month)
    if payload.is_locked is not None and current_user.role == "admin":
        submission.is_locked = payload.is_locked

    db.commit()
    db.refresh(submission)
    return SubmissionRead.from_orm(submission)


@router.delete("/{submission_id}")
def delete_submission(
    submission_id: int,
    db: Session = Depends(deps.get_db),
    current_user: models.User = Depends(deps.require_user),
) -> None:
    submission = db.get(models.Submission, submission_id)
    if not submission:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found")

    if current_user.role != "admin" and submission.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    db.delete(submission)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
