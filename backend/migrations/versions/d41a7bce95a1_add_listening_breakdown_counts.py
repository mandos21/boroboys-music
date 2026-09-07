"""add artist and album listening evidence counts

Revision ID: d41a7bce95a1
Revises: ae9c21bf4d80
Create Date: 2026-09-07 12:05:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d41a7bce95a1"
down_revision: str | None = "ae9c21bf4d80"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("listening_evidence", sa.Column("artist_playcount", sa.Integer()))
    op.add_column("listening_evidence", sa.Column("album_playcount", sa.Integer()))


def downgrade() -> None:
    op.drop_column("listening_evidence", "album_playcount")
    op.drop_column("listening_evidence", "artist_playcount")
