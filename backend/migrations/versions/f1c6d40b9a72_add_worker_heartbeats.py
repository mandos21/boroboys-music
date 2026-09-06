"""add worker heartbeats

Revision ID: f1c6d40b9a72
Revises: e5a71c9d3b40
Create Date: 2026-09-06 05:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f1c6d40b9a72"
down_revision: str | None = "e5a71c9d3b40"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "worker_heartbeats",
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column(
            "observed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("name"),
    )
    op.create_index("ix_worker_heartbeats_observed_at", "worker_heartbeats", ["observed_at"])


def downgrade() -> None:
    op.drop_index("ix_worker_heartbeats_observed_at", table_name="worker_heartbeats")
    op.drop_table("worker_heartbeats")
