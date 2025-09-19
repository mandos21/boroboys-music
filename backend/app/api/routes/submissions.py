from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api import deps
from app.db import crud, models
from app.schemas import (
    SubmissionCreate,
    SubmissionListResponse,
    SubmissionRead,
    SubmissionUpdate,
)
from app.services.playlist_manager import _normalize_month

router = APIRouter(prefix="/submissions")


@router.get("", response_model=SubmissionListResponse)
def list_submissions(
    month: Optional[datetime] = None,
    db: Session = Depends(deps.get_db),
    current_user: models.User = Depends(deps.require_user),
) -> SubmissionListResponse:
    month_filter = _normalize_month(month) if month else None

    statement = select(models.Submission).order_by(models.Submission.submission_month.desc())
    if month_filter:
        statement = statement.where(models.Submission.submission_month == month_filter)

    if current_user.role != "admin":
        statement = statement.where(models.Submission.user_id == current_user.id)

    submissions = db.scalars(statement).unique().all()
    return SubmissionListResponse(
        items=[SubmissionRead.from_orm(submission) for submission in submissions]
    )


@router.post("", response_model=SubmissionRead, status_code=status.HTTP_201_CREATED)
def create_submission(
    payload: SubmissionCreate,
    db: Session = Depends(deps.get_db),
    current_user: models.User = Depends(deps.require_user),
) -> SubmissionRead:
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
        genres={"items": track_data.genres} if track_data.genres else None,
        lastfm_tags={"tags": track_data.lastfm_tags} if track_data.lastfm_tags else None,
    )
    db.flush()

    submission = crud.create_or_update_submission(
        db,
        user=current_user,
        track=track,
        submission_month=payload.submission_month,
        notes=payload.notes,
        is_locked=False,
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
            genres={"items": track_data.genres} if track_data.genres else None,
            lastfm_tags={"tags": track_data.lastfm_tags} if track_data.lastfm_tags else None,
        )
        db.flush()
        submission.track_id = track.id

    if payload.notes is not None:
        submission.notes = payload.notes
    if payload.submission_month is not None:
        submission.submission_month = _normalize_month(payload.submission_month)
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
