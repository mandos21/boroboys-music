"""mark imported publications

Revision ID: e5a71c9d3b40
Revises: 2c8d14f7a6e9
Create Date: 2026-09-06 04:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e5a71c9d3b40"
down_revision: str | None = "2c8d14f7a6e9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "publications",
        sa.Column("is_imported", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.alter_column("publications", "is_imported", server_default=None)


def downgrade() -> None:
    op.drop_column("publications", "is_imported")
