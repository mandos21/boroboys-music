"""Import a private historical playlist CSV bundle into an existing series."""

from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import Series
from app.db.session import get_session_factory
from app.services.historical_import import (
    HistoricalImportError,
    HistoricalImportPlan,
    import_historical_playlist_bundle,
    load_historical_import_plan,
    validate_historical_import_target,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--series-slug", required=True, help="existing target series slug")
    parser.add_argument(
        "--publisher-account-id",
        type=uuid.UUID,
        required=True,
        help="Spotify account owned by a series administrator",
    )
    parser.add_argument(
        "--playlist-dir",
        type=Path,
        required=True,
        help="private directory of one playlist CSV per Spotify playlist ID",
    )
    parser.add_argument(
        "--identity-map",
        type=Path,
        required=True,
        help="private tab-separated email-to-OIDC-subject file",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate and report the import without writing any data",
    )
    parser.add_argument(
        "--oidc-issuer",
        help="issuer stored for imported users (defaults to OIDC_ISSUER_URL)",
    )
    args = parser.parse_args()

    try:
        configured_issuer = get_settings().oidc_issuer_url
        issuer = args.oidc_issuer or (
            str(configured_issuer).rstrip("/") if configured_issuer is not None else None
        )
        if not issuer:
            raise HistoricalImportError("OIDC issuer is required; set OIDC_ISSUER_URL or --oidc-issuer")
        with get_session_factory()() as db:
            series = db.scalar(select(Series).where(Series.slug == args.series_slug))
            if series is None:
                raise HistoricalImportError("series was not found")
            plan = load_historical_import_plan(args.playlist_dir, args.identity_map, series.timezone)
            validate_historical_import_target(
                db, args.series_slug, args.publisher_account_id, plan
            )
            if args.dry_run:
                _print_plan(plan)
                return 0
            result = import_historical_playlist_bundle(
                db, args.series_slug, args.publisher_account_id, issuer, plan
            )
            db.commit()
    except HistoricalImportError as error:
        print(f"Historical import refused: {error}", file=sys.stderr)
        return 2

    print(
        "Imported "
        f"{result.round_count} round(s), {result.publication_item_count} playlist item(s), "
        f"{result.submission_count} submission(s), and {result.contributor_count} contributor(s)."
    )
    return 0


def _print_plan(plan: HistoricalImportPlan) -> None:
    kind_counts = plan.kind_counts
    print(
        "Validated "
        f"{plan.playlist_count} playlist(s), {plan.playlist_item_count} playlist item(s), "
        f"{plan.submission_count} submission(s), and {plan.contributor_count} contributor(s)."
    )
    print(
        f"Round types: {kind_counts['monthly']} monthly, {kind_counts['year_end']} end-of-year. "
        "No data was written."
    )


if __name__ == "__main__":
    sys.exit(main())
