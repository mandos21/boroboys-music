"""add series identity, prompts, invites, and submission drafts

Revision ID: ae9c21bf4d80
Revises: 7a2e6f819cd3
Create Date: 2026-09-07 11:35:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "ae9c21bf4d80"
down_revision: str | None = "7a2e6f819cd3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("series", sa.Column("cover_image_url", sa.String(length=1000)))
    op.add_column("series", sa.Column("accent_color", sa.String(length=32)))
    op.add_column("rounds", sa.Column("prompt", sa.Text()))
    op.create_table(
        "submission_drafts",
        sa.Column("round_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("track", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("note", sa.Text()),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["round_id"], ["rounds.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("round_id", "user_id", name="uq_submission_drafts_round_user"),
    )
    op.create_index("ix_submission_drafts_round_id", "submission_drafts", ["round_id"])
    op.create_index("ix_submission_drafts_user_id", "submission_drafts", ["user_id"])
    op.create_table(
        "series_invites",
        sa.Column("series_id", sa.UUID(), nullable=False),
        sa.Column("created_by_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("max_uses", sa.Integer()),
        sa.Column("use_count", sa.Integer(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["series_id"], ["series.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_series_invites_token_hash"),
    )
    op.create_index("ix_series_invites_series_id", "series_invites", ["series_id"])
    op.create_index("ix_series_invites_expires_at", "series_invites", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_series_invites_expires_at", table_name="series_invites")
    op.drop_index("ix_series_invites_series_id", table_name="series_invites")
    op.drop_table("series_invites")
    op.drop_index("ix_submission_drafts_user_id", table_name="submission_drafts")
    op.drop_index("ix_submission_drafts_round_id", table_name="submission_drafts")
    op.drop_table("submission_drafts")
    op.drop_column("rounds", "prompt")
    op.drop_column("series", "accent_color")
    op.drop_column("series", "cover_image_url")
