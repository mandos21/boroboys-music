"""add publication item progress

Revision ID: 2c8d14f7a6e9
Revises: b84d86fc3b25
Create Date: 2026-09-06 03:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "2c8d14f7a6e9"
down_revision: str | None = "b84d86fc3b25"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "publication_items", sa.Column("published_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("publication_items", "published_at")
