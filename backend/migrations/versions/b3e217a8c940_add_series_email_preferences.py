"""Add personal email preferences per series.

Revision ID: b3e217a8c940
Revises: c8bbc2ca5e94
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b3e217a8c940"
down_revision: str | None = "c8bbc2ca5e94"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "series_notification_preferences",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("series_id", sa.UUID(), nullable=False),
        sa.Column("notify_reminder_emails", sa.Boolean(), nullable=False),
        sa.Column("notify_round_published_emails", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["series_id"], ["series.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "series_id", name="uq_series_notification_preferences_user_series"),
    )
    op.create_index("ix_series_notification_preferences_series_id", "series_notification_preferences", ["series_id"])


def downgrade() -> None:
    op.drop_table("series_notification_preferences")
