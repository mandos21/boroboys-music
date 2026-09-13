"""claim the joe schmoe placeholder account as kevin reynolds' real identity

Revision ID: e690bbf0ab1b
Revises: c7d2e4f6a8b0
Create Date: 2026-09-13 00:00:00.000000

"Joe Schmoe" was a placeholder account used to attribute Kevin's
contributions during historical import, before his real identity was
known. Kevin's real Keycloak account now exists
(kreynolds4142@gmail.com, sub b4f6e9c8-7c49-4052-812f-9e5e5732b7af) but
he has not logged into the app with it yet. Rather than reassigning
every row Joe touched onto a separate Kevin account, this repoints the
placeholder's own OIDC identity and email onto Kevin's real one, so his
first real login resolves to this existing account - already carrying
his history - instead of creating a second, empty one. The account's
row id, and therefore everything already attributed to it, does not
change.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e690bbf0ab1b"
down_revision: str | None = "c7d2e4f6a8b0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PLACEHOLDER_DISPLAY_NAME = "Joe Schmoe"
KEVIN_OIDC_ISSUER = "https://id.dege.app/realms/theborocrew"
KEVIN_OIDC_SUBJECT = "b4f6e9c8-7c49-4052-812f-9e5e5732b7af"
KEVIN_EMAIL = "kreynolds4142@gmail.com"
KEVIN_DISPLAY_NAME = "Kevin Reynolds"


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

    conflict = connection.execute(
        sa.text("SELECT 1 FROM users WHERE oidc_issuer = :issuer AND oidc_subject = :subject"),
        {"issuer": KEVIN_OIDC_ISSUER, "subject": KEVIN_OIDC_SUBJECT},
    ).scalar_one_or_none()
    if conflict is not None:
        raise RuntimeError(
            "a user already exists with Kevin's real OIDC identity; refusing to overwrite it"
        )

    connection.execute(
        sa.text(
            "UPDATE users SET oidc_issuer = :issuer, oidc_subject = :subject, "
            "email = :email, display_name = :display_name WHERE id = :joe_id"
        ),
        {
            "issuer": KEVIN_OIDC_ISSUER,
            "subject": KEVIN_OIDC_SUBJECT,
            "email": KEVIN_EMAIL,
            "display_name": KEVIN_DISPLAY_NAME,
            "joe_id": joe_id,
        },
    )


def downgrade() -> None:
    # The placeholder's original OIDC identity is not recoverable once
    # overwritten, so this cannot be safely reversed.
    pass
