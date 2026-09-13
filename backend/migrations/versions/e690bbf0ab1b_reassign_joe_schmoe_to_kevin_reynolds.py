"""reassign joe schmoe's historical data to kevin reynolds' real account

Revision ID: e690bbf0ab1b
Revises: c7d2e4f6a8b0
Create Date: 2026-09-13 00:00:00.000000

"Joe Schmoe" was a placeholder account used to attribute Kevin's
contributions during historical import, before his real email address was
known. Kevin's real account (kreynolds4142@gmail.com) now exists, so this
one-time, idempotent step reassigns everything attributed to the
placeholder onto it and removes the placeholder.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e690bbf0ab1b"
down_revision: str | None = "c7d2e4f6a8b0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

KEVIN_USER_ID = uuid.UUID("b4f6e9c8-7c49-4052-812f-9e5e5732b7af")
PLACEHOLDER_DISPLAY_NAME = "Joe Schmoe"


def upgrade() -> None:
    connection = op.get_bind()
    placeholder_ids = (
        connection.execute(
            sa.text("SELECT id FROM users WHERE display_name = :name"),
            {"name": PLACEHOLDER_DISPLAY_NAME},
        )
        .scalars()
        .all()
    )
    if not placeholder_ids:
        # Already migrated (or this environment never had the placeholder);
        # nothing to do, and this step must be safe to run again.
        return
    if len(placeholder_ids) > 1:
        raise RuntimeError(
            f"expected exactly one '{PLACEHOLDER_DISPLAY_NAME}' user, found "
            f"{len(placeholder_ids)}; refusing to guess which one to reassign"
        )
    joe_id = placeholder_ids[0]

    kevin_exists = connection.execute(
        sa.text("SELECT 1 FROM users WHERE id = :kevin_id"), {"kevin_id": KEVIN_USER_ID}
    ).scalar_one_or_none()
    if kevin_exists is None:
        raise RuntimeError(f"target user {KEVIN_USER_ID} does not exist; refusing to reassign")

    # Round membership: where Kevin is already independently a member of a
    # round Joe was also in, drop Joe's row rather than collide with it;
    # otherwise repoint Joe's row onto Kevin.
    connection.execute(
        sa.text(
            "DELETE FROM round_members WHERE user_id = :joe_id AND round_id IN "
            "(SELECT round_id FROM round_members WHERE user_id = :kevin_id)"
        ),
        {"joe_id": joe_id, "kevin_id": KEVIN_USER_ID},
    )
    connection.execute(
        sa.text("UPDATE round_members SET user_id = :kevin_id WHERE user_id = :joe_id"),
        {"kevin_id": KEVIN_USER_ID, "joe_id": joe_id},
    )

    # Contributor group membership: same duplicate-avoidance as above.
    connection.execute(
        sa.text(
            "DELETE FROM contributor_group_members WHERE user_id = :joe_id AND group_id IN "
            "(SELECT group_id FROM contributor_group_members WHERE user_id = :kevin_id)"
        ),
        {"joe_id": joe_id, "kevin_id": KEVIN_USER_ID},
    )
    connection.execute(
        sa.text("UPDATE contributor_group_members SET user_id = :kevin_id WHERE user_id = :joe_id"),
        {"kevin_id": KEVIN_USER_ID, "joe_id": joe_id},
    )

    # The historical submissions and publication credits themselves.
    connection.execute(
        sa.text("UPDATE submissions SET contributor_id = :kevin_id WHERE contributor_id = :joe_id"),
        {"kevin_id": KEVIN_USER_ID, "joe_id": joe_id},
    )
    connection.execute(
        sa.text(
            "UPDATE publication_items SET contributor_id = :kevin_id WHERE contributor_id = :joe_id"
        ),
        {"kevin_id": KEVIN_USER_ID, "joe_id": joe_id},
    )

    # Nothing should reference the placeholder any more; remove it outright
    # rather than leave a dangling look-alike account behind. Any surviving,
    # unanticipated reference makes this fail loudly instead of silently
    # losing data.
    connection.execute(sa.text("DELETE FROM users WHERE id = :joe_id"), {"joe_id": joe_id})


def downgrade() -> None:
    # Which rows originated from the placeholder is not recoverable once
    # merged into Kevin's account, so this cannot be safely reversed.
    pass
