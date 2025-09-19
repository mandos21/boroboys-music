from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api import deps
from app.db import crud, models
from app.core.dates import current_month_start
from app.schemas import (
    AdminMonthSummary,
    InviteCreateRequest,
    InviteListResponse,
    InviteRead,
    ManualReleaseRequest,
    MonthSettingsRead,
    MonthSettingsUpdate,
    PlaylistRead,
    SubmissionRead,
)
from app.services.playlist_manager import PlaylistManager

router = APIRouter(prefix="/admin")


@router.get("/invites", response_model=InviteListResponse)
def list_invites(
    include_used: bool = False,
    db: Session = Depends(deps.get_db),
    _: models.User = Depends(deps.require_admin),
) -> InviteListResponse:
    invites = crud.list_invites(db, include_used=include_used)
    return InviteListResponse(items=[InviteRead.from_orm(invite) for invite in invites])


@router.post("/invites", response_model=InviteRead, status_code=status.HTTP_201_CREATED)
def create_invite(
    payload: InviteCreateRequest,
    db: Session = Depends(deps.get_db),
    current_user: models.User = Depends(deps.require_admin),
) -> InviteRead:
    invite = crud.create_invite(
        db,
        created_by=current_user,
        email=payload.email,
        role=payload.role,
        expires_in_days=payload.expires_in_days,
    )
    db.commit()
    db.refresh(invite)
    return InviteRead.from_orm(invite)


@router.get("/months/current", response_model=AdminMonthSummary)
def read_current_month(
    db: Session = Depends(deps.get_db),
    _: models.User = Depends(deps.require_admin),
) -> AdminMonthSummary:
    month = current_month_start()
    settings = crud.get_or_create_month_settings(db, month)
    db.commit()
    db.refresh(settings)
    submissions = crud.list_submissions_for_month(db, month)
    playlist = crud.get_playlist_by_month(db, month)
    return AdminMonthSummary(
        settings=MonthSettingsRead.from_orm(settings),
        submissions=[SubmissionRead.from_orm(item) for item in submissions],
        released=playlist is not None,
    )


@router.put("/months/current", response_model=MonthSettingsRead)
def update_current_month(
    payload: MonthSettingsUpdate,
    db: Session = Depends(deps.get_db),
    _: models.User = Depends(deps.require_admin),
) -> MonthSettingsRead:
    month = current_month_start()
    settings = crud.update_month_settings(
        db,
        month,
        submission_limit=payload.submission_limit,
        spotify_owner_id=payload.spotify_owner_id,
    )
    db.commit()
    db.refresh(settings)
    return MonthSettingsRead.from_orm(settings)


@router.post("/months/release", response_model=PlaylistRead)
def release_current_month(
    payload: ManualReleaseRequest | None = None,
    manager: PlaylistManager = Depends(deps.get_playlist_manager),
    db: Session = Depends(deps.get_db),
    current_user: models.User = Depends(deps.require_admin),
) -> PlaylistRead:
    month = current_month_start()
    settings = crud.get_or_create_month_settings(db, month)
    db.commit()
    db.refresh(settings)
    owner_id = (
        payload.spotify_owner_id
        if payload and payload.spotify_owner_id is not None
        else settings.spotify_owner_id
    )

    playlist = manager.finalize_month(
        month,
        admin_user_id=current_user.id,
        spotify_owner_id=owner_id,
    )
    if playlist is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No submissions available to release for the current month.",
        )

    refreshed = crud.get_playlist_by_month(db, month) or playlist
    return PlaylistRead.from_orm(refreshed)
