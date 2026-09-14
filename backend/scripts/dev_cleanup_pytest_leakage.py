"""One-off cleanup: remove pytest fixture data that leaked into the real dev database.

NOT part of the product. At some point before this script existed, the test
suite appears to have run against `DATABASE_URL` instead of
`TEST_DATABASE_URL` (today's `conftest.py` refuses to start without a
`TEST_DATABASE_URL` ending in `_test`, so this shouldn't be possible anymore),
leaving thousands of fixture-shaped rows behind: series named things like
"Queue d0a358c66fe4" and users under the fixture issuer
"https://issuer.test".

This deletes:
  - every Series whose name ends in a 12-hex-character suffix (conftest.py's
    `make_series` and most test files' own fixtures append exactly this kind
    of suffix; verified zero overlap with real data before writing this -
    every one of these series' rounds/members/submissions trace back to
    `https://issuer.test` users only, never a real account), which cascades
    away their rounds, round members, submissions, publications, and
    attribution games/guesses;
  - every remaining User row under `oidc_issuer = 'https://issuer.test'`.

Explicitly leaves alone: any series not matching that suffix pattern
(including hand-created "New series" experiments), and every real account.

Prints before/after counts. Not idempotent in a meaningful way - there's
nothing left to clean up once it's run once.
"""

from __future__ import annotations

from sqlalchemy import delete, func, select

from app.db.models import Series, User
from app.db.session import get_session_factory

_PYTEST_SUFFIX = r"[0-9a-f]{12}$"


def main() -> None:
    with get_session_factory()() as db:
        before_series = db.scalar(select(func.count()).select_from(Series))
        before_users = db.scalar(select(func.count()).select_from(User))

        junk_series_ids = select(Series.id).where(Series.name.op("~")(_PYTEST_SUFFIX))
        deleted_series = db.execute(delete(Series).where(Series.id.in_(junk_series_ids)))
        deleted_users = db.execute(delete(User).where(User.oidc_issuer == "https://issuer.test"))
        db.commit()

        after_series = db.scalar(select(func.count()).select_from(Series))
        after_users = db.scalar(select(func.count()).select_from(User))

    print(f"Series:  {before_series} -> {after_series} (deleted {deleted_series.rowcount})")
    print(f"Users:   {before_users} -> {after_users} (deleted {deleted_users.rowcount})")


if __name__ == "__main__":
    main()
