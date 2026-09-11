"""add round open announcement claim

Revision ID: c7d2e4f6a8b0
Revises: ba80cf6b4e85
Create Date: 2026-09-11 10:20:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c7d2e4f6a8b0"
down_revision: str | None = "ba80cf6b4e85"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "rounds", sa.Column("opened_announced_at", sa.DateTime(timezone=True), nullable=True)
    )
    # Every round that has already opened was either announced by the old
    # transition-based code or is history; none of them should be announced
    # again on the first scheduler pass after this deploys.
    op.execute(
        "UPDATE rounds SET opened_announced_at = now() WHERE status NOT IN ('DRAFT', 'SCHEDULED')"
    )


def downgrade() -> None:
    op.drop_column("rounds", "opened_announced_at")
