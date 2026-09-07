"""add durable publication execution leases

Revision ID: c52d77f9a1b4
Revises: d41a7bce95a1
Create Date: 2026-09-07 14:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c52d77f9a1b4"
down_revision: str | None = "d41a7bce95a1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("publications", sa.Column("execution_token", sa.String(length=128)))
    op.add_column(
        "publications", sa.Column("execution_lease_expires_at", sa.DateTime(timezone=True))
    )
    op.create_index(
        "ix_publications_execution_lease_expires_at",
        "publications",
        ["execution_lease_expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_publications_execution_lease_expires_at", table_name="publications")
    op.drop_column("publications", "execution_lease_expires_at")
    op.drop_column("publications", "execution_token")
