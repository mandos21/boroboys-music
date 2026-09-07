"""Populate missing track artwork from Spotify using a linked publisher account."""

from __future__ import annotations

import argparse
import sys
import uuid

import httpx
from sqlalchemy import select

from app.db.models import Track
from app.db.session import get_session_factory
from app.services import spotify
from app.services.publications import PublicationError, get_spotify_access_token


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--publisher-account-id",
        type=uuid.UUID,
        required=True,
        help="linked Spotify account that is allowed to read Spotify metadata",
    )
    args = parser.parse_args()

    try:
        with get_session_factory()() as db:
            tracks = list(
                db.scalars(
                    select(Track)
                    .where(Track.artwork_url.is_(None))
                    .order_by(Track.spotify_track_id)
                )
            )
            token = get_spotify_access_token(db, args.publisher_account_id)
            updated = _backfill_artwork(tracks, token)
            db.commit()
    except (PublicationError, spotify.SpotifyError, httpx.HTTPError) as error:
        print(f"Artwork backfill failed: {error}", file=sys.stderr)
        return 2

    print(f"Updated artwork for {updated} of {len(tracks)} track(s) missing artwork.")
    return 0


def _backfill_artwork(tracks: list[Track], access_token: str) -> int:
    by_spotify_id = {track.spotify_track_id: track for track in tracks}
    updated = 0
    track_ids = list(by_spotify_id)
    for start in range(0, len(track_ids), 50):
        for item in spotify.tracks_by_id(access_token, track_ids[start : start + 50]):
            track_id = item.get("id")
            album = item.get("album")
            images = album.get("images") if isinstance(album, dict) else None
            if not isinstance(track_id, str) or not isinstance(images, list) or not images:
                continue
            image = images[0]
            url = image.get("url") if isinstance(image, dict) else None
            track = by_spotify_id.get(track_id)
            if track is not None and isinstance(url, str):
                track.artwork_url = url
                updated += 1
    return updated


if __name__ == "__main__":
    sys.exit(main())
