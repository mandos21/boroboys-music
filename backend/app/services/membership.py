"""Small shared operations for durable series membership."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ContributorGroup, ContributorGroupMember


def ensure_default_series_membership(db: Session, series_id: uuid.UUID, user_id: uuid.UUID) -> None:
    """Add a person to the conventional all-series group if they are not already in it."""
    group = db.scalar(
        select(ContributorGroup).where(
            ContributorGroup.series_id == series_id,
            ContributorGroup.name == "Series members",
        )
    )
    if group is None:
        group = ContributorGroup(series_id=series_id, name="Series members")
        db.add(group)
        db.flush()
    if db.scalar(
        select(ContributorGroupMember.id).where(
            ContributorGroupMember.group_id == group.id,
            ContributorGroupMember.user_id == user_id,
        )
    ) is None:
        db.add(ContributorGroupMember(group_id=group.id, user_id=user_id))
