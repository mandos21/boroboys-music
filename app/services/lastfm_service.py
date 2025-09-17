"""Last.fm integration helpers built on top of pylast."""
from __future__ import annotations

from typing import Dict, List, Optional

from loguru import logger
from pylast import LastFMNetwork, NetworkError

from app.config import get_settings


class LastFMService:
    """Wrapper around Last.fm network interactions."""

    def __init__(self, network: LastFMNetwork):
        self.network = network

    @classmethod
    def from_settings(cls) -> "LastFMService":
        settings = get_settings()
        network = LastFMNetwork(
            api_key=settings.lastfm_api_key,
            api_secret=settings.lastfm_shared_secret,
            username=settings.lastfm_username,
        )
        return cls(network)

    def get_user_track_playcount(
        self,
        username: str,
        artist_name: str,
        track_name: str,
    ) -> Optional[int]:
        try:
            user = self.network.get_user(username)
            track = self.network.get_track(artist_name, track_name)
            playcounts = user.get_track_playcount(track)
            return int(playcounts)
        except NetworkError as exc:
            logger.warning("Failed to fetch playcount for %s - %s: %s", artist_name, track_name, exc)
            return None

    def get_track_tags(self, artist_name: str, track_name: str) -> List[str]:
        try:
            track = self.network.get_track(artist_name, track_name)
            tags = track.get_top_tags(limit=10)
            return [tag.item.name for tag in tags]
        except NetworkError as exc:
            logger.debug("Failed to fetch tags for %s - %s: %s", artist_name, track_name, exc)
            return []

    def get_recent_tracks(self, username: str, limit: int = 10) -> List[Dict[str, str]]:
        try:
            user = self.network.get_user(username)
            recent = user.get_recent_tracks(limit=limit)
            return [
                {
                    "artist": item.track.artist.name,
                    "track": item.track.title,
                    "played_at": item.playback_date,
                }
                for item in recent
            ]
        except NetworkError as exc:
            logger.debug("Failed to fetch recent tracks for %s: %s", username, exc)
            return []