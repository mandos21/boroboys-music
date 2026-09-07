"""manage the Procrastinate schema through Alembic

Revision ID: d84e1f2a6b3c
Revises: c52d77f9a1b4
Create Date: 2026-09-07 14:10:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from procrastinate.schema import SchemaManager

revision: str = "d84e1f2a6b3c"
down_revision: str | None = "c52d77f9a1b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Install the pinned Procrastinate schema only for a new database.

    Its CLI `schema --apply` command is explicitly intended for an empty
    database and cannot be used during every container startup. The package is
    locked in poetry.lock; upgrading it requires a deliberate follow-up
    Alembic migration for its DDL changes.
    """
    connection = op.get_bind()
    installed = connection.scalar(sa.text("SELECT to_regclass('public.procrastinate_jobs')"))
    if installed is None:
        # Procrastinate's PostgreSQL functions contain `%` operators. Passing
        # its multi-statement DDL through SQLAlchemy's psycopg executor makes
        # those look like DB-API placeholders, so execute the locked script on
        # the same transaction's raw cursor instead.
        with connection.connection.cursor() as cursor:
            cursor.execute(SchemaManager.get_schema())


def downgrade() -> None:
    # Queue tables can contain operational history. Deliberately retain them
    # rather than making a domain downgrade destructively drop pending work.
    pass
