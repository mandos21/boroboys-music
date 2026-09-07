"""store linked-provider profile images

Revision ID: c4f19aa827de
Revises: d3a9e5f0b127
Create Date: 2026-09-07 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c4f19aa827de"
down_revision: str | None = "d3a9e5f0b127"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("external_accounts", sa.Column("profile_image_url", sa.String(1000)))


def downgrade() -> None:
    op.drop_column("external_accounts", "profile_image_url")
