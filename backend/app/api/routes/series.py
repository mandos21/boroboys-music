"""Contributor-visible series history without leaking other private round groups."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.api.deps import DbSession, get_current_user
from app.db.models import PlatformRole, Round, RoundMember, Series, SeriesAdmin, User

router = APIRouter(prefix="/series", tags=["series"])


@router.get("/{series_id}")
def get_series_history(
    series_id: uuid.UUID,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, object]:
    """Return rounds visible to the caller within one series.

    Series may run overlapping contributor groups. A normal contributor sees
    only their active materialized memberships; platform and series admins can
    inspect the complete series history.
    """
    series = db.get(Series, series_id)
    if series is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="series not found")
    is_admin = user.platform_role is PlatformRole.ADMIN or (
        db.scalar(
            select(SeriesAdmin.id).where(
                SeriesAdmin.series_id == series_id,
                SeriesAdmin.user_id == user.id,
            )
        )
        is not None
    )
    statement = select(Round).where(Round.series_id == series_id)
    if not is_admin:
        statement = (
            statement.join(RoundMember, RoundMember.round_id == Round.id)
            .where(
                RoundMember.user_id == user.id,
                RoundMember.removed_at.is_(None),
            )
            .distinct()
        )
    rounds = list(db.scalars(statement.order_by(Round.opens_at.desc())))
    if not is_admin and not rounds:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="series access required")
    return {
        "id": str(series.id),
        "name": series.name,
        "description": series.description,
        "timezone": series.timezone,
        "rounds": [
            {
                "id": str(round_.id),
                "title": round_.title,
                "status": round_.status.value,
                "opensAt": round_.opens_at.isoformat(),
                "closesAt": round_.closes_at.isoformat(),
                "publishAt": round_.publish_at.isoformat(),
            }
            for round_ in rounds
        ],
    }
