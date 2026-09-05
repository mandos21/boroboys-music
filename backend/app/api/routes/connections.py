"""User-managed external account links and listening-evidence visibility."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import DbSession, get_current_user, require_csrf
from app.db.models import EvidenceVisibility, ExternalAccount, ExternalProvider, User

router = APIRouter(
    prefix="/connections", tags=["connections"], dependencies=[Depends(require_csrf)]
)


class LastfmLink(BaseModel):
    username: str = Field(min_length=1, max_length=255)
    visibility: EvidenceVisibility = EvidenceVisibility.ROUND_MEMBERS


class VisibilityUpdate(BaseModel):
    visibility: EvidenceVisibility


@router.put("/lastfm", status_code=status.HTTP_201_CREATED)
def link_lastfm(
    payload: LastfmLink,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, str]:
    account = db.scalar(
        select(ExternalAccount).where(
            ExternalAccount.provider == ExternalProvider.LASTFM,
            ExternalAccount.provider_subject == payload.username,
        )
    )
    if account is not None and account.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Last.fm account is already linked"
        )
    if account is None:
        account = ExternalAccount(
            user_id=user.id,
            provider=ExternalProvider.LASTFM,
            provider_subject=payload.username,
            display_name=payload.username,
            evidence_visibility=payload.visibility,
        )
        db.add(account)
    else:
        account.evidence_visibility = payload.visibility
        account.is_active = True
        account.disconnected_at = None
    db.commit()
    return {"id": str(account.id), "provider": account.provider.value}


@router.patch("/{account_id}/visibility")
def update_visibility(
    account_id: uuid.UUID,
    payload: VisibilityUpdate,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, str]:
    account = db.get(ExternalAccount, account_id)
    if account is None or account.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="linked account not found"
        )
    account.evidence_visibility = payload.visibility
    db.commit()
    return {"id": str(account.id), "visibility": account.evidence_visibility.value}
