"""harden publication integrity

Revision ID: d3a9e5f0b127
Revises: f1c6d40b9a72
Create Date: 2026-09-06 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d3a9e5f0b127"
down_revision: str | None = "f1c6d40b9a72"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("rounds", sa.Column("successor_of_round_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_rounds_successor_of_rounds",
        "rounds",
        "rounds",
        ["successor_of_round_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_unique_constraint("uq_rounds_successor_of", "rounds", ["successor_of_round_id"])
    op.create_unique_constraint(
        "uq_rounds_series_published_sequence",
        "rounds",
        ["series_id", "published_sequence"],
    )
    op.add_column(
        "publications",
        sa.Column(
            "retirement_requested",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.alter_column("publications", "retirement_requested", server_default=None)


def downgrade() -> None:
    op.drop_column("publications", "retirement_requested")
    op.drop_constraint("uq_rounds_series_published_sequence", "rounds", type_="unique")
    op.drop_constraint("uq_rounds_successor_of", "rounds", type_="unique")
    op.drop_constraint("fk_rounds_successor_of_rounds", "rounds", type_="foreignkey")
    op.drop_column("rounds", "successor_of_round_id")
