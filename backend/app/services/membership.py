"""Small shared operations for durable series membership."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ContributorGroup, ContributorGroupMember, Round, RoundMember, RoundStatus


def ensure_default_series_membership(db: Session, series_id: uuid.UUID, user_id: uuid.UUID) -> None:
    """Add a person to the conventional all-series group if they are not already in it.

    Also enrolls them in whichever round is currently open for the series, so
    joining mid-round does not mean waiting for the next one to have anything
    to submit to.
    """
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
    if (
        db.scalar(
            select(ContributorGroupMember.id).where(
                ContributorGroupMember.group_id == group.id,
                ContributorGroupMember.user_id == user_id,
            )
        )
        is None
    ):
        db.add(ContributorGroupMember(group_id=group.id, user_id=user_id))
    for round_id in db.scalars(
        select(Round.id).where(Round.series_id == series_id, Round.status == RoundStatus.OPEN)
    ):
        membership = db.scalar(
            select(RoundMember).where(
                RoundMember.round_id == round_id, RoundMember.user_id == user_id
            )
        )
        if membership is None:
            db.add(RoundMember(round_id=round_id, user_id=user_id))
        elif membership.removed_at is not None:
            membership.removed_at = None
