"""Import a private historical playlist CSV bundle into an existing series.

Spotify is queried only to cache durable album-art URLs alongside the imported
tracks; the source CSV remains authoritative for playlist content and order.
"""

from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Series
from app.db.session import get_session_factory
from app.services import spotify
from app.services.historical_import import (
    HistoricalImportError,
    HistoricalImportPlan,
    import_historical_playlist_bundle,
    load_historical_import_plan,
    validate_historical_import_target,
)
from app.services.publications import PublicationError, get_spotify_access_token


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
            artwork_by_track_id = _spotify_artwork_by_track_id(db, args.publisher_account_id, plan)
            result = import_historical_playlist_bundle(
                db, args.series_slug, args.publisher_account_id, issuer, plan, artwork_by_track_id
            )
            db.commit()
    except (HistoricalImportError, PublicationError, spotify.SpotifyError, httpx.HTTPError) as error:
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


def _spotify_artwork_by_track_id(
    db: Session, publisher_account_id: uuid.UUID, plan: HistoricalImportPlan
) -> dict[str, str]:
    """Fetch durable album art while the importer still has a Spotify credential."""
    token = get_spotify_access_token(db, publisher_account_id)
    artwork: dict[str, str] = {}
    for round_plan in plan.rounds:
        snapshot = spotify.playlist_snapshot(token, round_plan.playlist.spotify_playlist_id)
        for track in snapshot["items"]:
            if not isinstance(track, dict) or not isinstance(track.get("id"), str):
                continue
            album = track.get("album")
            images = album.get("images") if isinstance(album, dict) else None
            if isinstance(images, list) and images and isinstance(images[0], dict):
                url = images[0].get("url")
                if isinstance(url, str):
                    artwork[track["id"]] = url
    return artwork


if __name__ == "__main__":
    sys.exit(main())
