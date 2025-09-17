"""Spotify integration helpers built on top of Spotipy."""
from __future__ import annotations

from typing import Any, Iterable, List, Optional

from loguru import logger
from spotipy import Spotify
from spotipy.oauth2 import SpotifyClientCredentials

from app.config import get_settings


class SpotifyService:
    """Lightweight wrapper around the Spotify Web API."""

    def __init__(self, client: Spotify):
        self.client = client

    @classmethod
    def from_app_credentials(cls) -> "SpotifyService":
        """Instantiate the service using client credentials flow."""

        settings = get_settings()
        auth_manager = SpotifyClientCredentials(
            client_id=settings.spotify_client_id, client_secret=settings.spotify_client_secret
        )
        client = Spotify(auth_manager=auth_manager)
        return cls(client)

    @classmethod
    def from_user_token(cls, access_token: str) -> "SpotifyService":
        client = Spotify(auth=access_token)
        return cls(client)

    def search_tracks(self, query: str, limit: int = 10) -> List[dict[str, Any]]:
        logger.debug("Searching Spotify for query='{}'", query)
        response = self.client.search(q=query, type="track", limit=limit)
        return response.get("tracks", {}).get("items", [])

    def fetch_track(self, track_id: str) -> Optional[dict[str, Any]]:
        try:
            return self.client.track(track_id)
        except Exception as exc:
            logger.warning("Unable to fetch track {}: {}", track_id, exc)
            return None

    def current_user(self) -> dict[str, Any]:
        return self.client.current_user()

    def create_playlist(
        self,
        user_spotify_id: str,
        name: str,
        description: str,
        *,
        public: bool = False,
    ) -> dict[str, Any]:
        logger.info("Creating Spotify playlist '{}' for user '{}'", name, user_spotify_id)
        return self.client.user_playlist_create(
            user=user_spotify_id, name=name, public=public, description=description
        )

    def add_tracks_to_playlist(
        self,
        playlist_id: str,
        track_ids: Iterable[str],
    ) -> None:
        track_list = list(track_ids)
        if not track_list:
            logger.debug("No tracks provided for playlist {}", playlist_id)
            return
        logger.info("Adding %d tracks to Spotify playlist %s", len(track_list), playlist_id)
        self.client.playlist_add_items(playlist_id, track_list)
