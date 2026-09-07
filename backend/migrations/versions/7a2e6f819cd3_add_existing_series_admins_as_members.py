"""add existing series administrators as default members

Revision ID: 7a2e6f819cd3
Revises: c4f19aa827de
Create Date: 2026-09-07 02:25:00.000000
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7a2e6f819cd3"
down_revision: str | None = "c4f19aa827de"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    assignments = connection.execute(
        sa.text("SELECT series_id, user_id FROM series_admins")
    ).mappings()
    for assignment in assignments:
        series_id, user_id = assignment["series_id"], assignment["user_id"]
        group_id = connection.execute(
            sa.text(
                "SELECT id FROM contributor_groups "
                "WHERE series_id = :series_id AND name = 'Series members'"
            ),
            {"series_id": series_id},
        ).scalar_one_or_none()
        if group_id is None:
            group_id = uuid.uuid4()
            connection.execute(
                sa.text(
                    "INSERT INTO contributor_groups (id, series_id, name) "
                    "VALUES (:id, :series_id, 'Series members')"
                ),
                {"id": group_id, "series_id": series_id},
            )
        exists = connection.execute(
            sa.text(
                "SELECT 1 FROM contributor_group_members "
                "WHERE group_id = :group_id AND user_id = :user_id"
            ),
            {"group_id": group_id, "user_id": user_id},
        ).scalar_one_or_none()
        if exists is None:
            connection.execute(
                sa.text(
                    "INSERT INTO contributor_group_members (id, group_id, user_id) "
                    "VALUES (:id, :group_id, :user_id)"
                ),
                {"id": uuid.uuid4(), "group_id": group_id, "user_id": user_id},
            )


def downgrade() -> None:
    # Membership removals are user-facing state and cannot be safely inferred.
    pass
