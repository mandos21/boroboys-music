from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api import deps
from app.db import crud, models
from app.schemas import UserListResponse, UserRead

router = APIRouter(prefix="/users")


@router.get("/me", response_model=UserRead)
def read_current_user(user: models.User = Depends(deps.require_user)) -> UserRead:
    return UserRead.from_orm(user)


@router.get("", response_model=UserListResponse)
def list_users(
    db: Session = Depends(deps.get_db),
    _: models.User = Depends(deps.require_admin),
) -> UserListResponse:
    users = crud.list_users(db)
    return UserListResponse(items=[UserRead.from_orm(user) for user in users])


@router.get("/{user_id}", response_model=UserRead)
def read_user(
    user_id: int,
    db: Session = Depends(deps.get_db),
    _: models.User = Depends(deps.require_admin),
) -> UserRead:
    user = db.get(models.User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return UserRead.from_orm(user)
