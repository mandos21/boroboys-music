"""Playlist orchestration helpers bridging the database and external services."""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from loguru import logger
from sqlalchemy import Select, select

from app.db import crud, models
from app.db.session import session_scope
from app.services.lastfm_service import LastFMService
from app.services.spotify_service import SpotifyService


def _normalize_month(value: date | datetime) -> datetime:
    base = value if isinstance(value, datetime) else datetime(value.year, value.month, 1)
    return base.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


class PlaylistManager:
    """Coordinates monthly playlists across Spotify, Last.fm, and PostgreSQL."""

    def __init__(
        self,
        spotify_service: SpotifyService,
        *,
        lastfm_service: Optional[LastFMService] = None,
    ) -> None:
        self.spotify_service = spotify_service
        self.lastfm_service = lastfm_service

    def finalize_month(
        self,
        target_month: date | datetime,
        *,
        admin_user_id: Optional[int] = None,
        spotify_owner_id: Optional[str] = None,
    ) -> Optional[models.Playlist]:
        month_start = _normalize_month(target_month)
        with session_scope() as session:
            playlist = crud.get_playlist_by_month(session, month_start)
            if playlist:
                logger.info("Playlist for {} already exists", month_start.strftime("%Y-%m"))
                return playlist

            submissions_statement: Select[tuple[models.Submission]] = select(models.Submission).where(
                models.Submission.submission_month == month_start, models.Submission.is_locked.is_(False)
            )
            submissions = session.scalars(submissions_statement).all()
            if not submissions:
                logger.info("No submissions found for {}", month_start.strftime("%Y-%m"))
                return None

            playlist_name = month_start.strftime("Boro Boys %B %Y")
            description = "Community submissions for {}".format(month_start.strftime("%B %Y"))
            spotify_playlist_id: Optional[str] = None

            if spotify_owner_id:
                created = self.spotify_service.create_playlist(
                    user_spotify_id=spotify_owner_id,
                    name=playlist_name,
                    description=description,
                    public=False,
                )
                spotify_playlist_id = created.get("id")
                track_uris = [
                    f"spotify:track:{submission.track.spotify_track_id}"
                    for submission in submissions
                    if submission.track.spotify_track_id
                ]
                if track_uris:
                    self.spotify_service.add_tracks_to_playlist(
                        playlist_id=spotify_playlist_id,
                        track_ids=track_uris,
                    )

            playlist = models.Playlist(
                name=playlist_name,
                description=description,
                month=month_start,
                spotify_playlist_id=spotify_playlist_id,
                finalized_by=admin_user_id,
            )
            session.add(playlist)
            session.flush()

            for index, submission in enumerate(submissions, start=1):
                session.add(
                    models.PlaylistTrack(
                        playlist=playlist,
                        track=submission.track,
                        position=index,
                    )
                )
                submission.is_locked = True

            logger.info(
                "Finalized playlist for {} with {} submissions",
                month_start.strftime("%Y-%m"),
                len(submissions),
            )
            return playlist

    def sync_lastfm_stats_for_submission(self, submission_id: int) -> None:
        if self.lastfm_service is None:
            logger.debug("Last.fm service not configured; skipping stats sync for submission {}", submission_id)
            return

        with session_scope() as session:
            submission = session.get(models.Submission, submission_id)
            if submission is None:
                logger.warning("Submission {} not found", submission_id)
                return

            user = submission.user
            track = submission.track
            if not user.lastfm_username:
                logger.debug("User {} has no Last.fm username; skipping", user.username)
                return

            playcount = self.lastfm_service.get_user_track_playcount(
                user.lastfm_username,
                artist_name=track.artist,
                track_name=track.name,
            )
            tags = self.lastfm_service.get_track_tags(track.artist, track.name)

            submission.track.lastfm_tags = {"tags": tags}

            stat = models.ListeningStat(
                user_id=user.id,
                track_id=track.id,
                lastfm_playcount=playcount or 0,
                snapshot_at=datetime.utcnow(),
            )
            session.add(stat)
            logger.info("Updated Last.fm stats for submission {}", submission_id)