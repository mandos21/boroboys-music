from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api import deps
from app.db import crud, models
from app.schemas import InviteCreateRequest, InviteListResponse, InviteRead

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
