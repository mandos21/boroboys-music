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

    @staticmethod
    def pick_image_url(images: Optional[List[dict[str, Any]]]) -> Optional[str]:
        if not images:
            return None
        for image in images:
            url = image.get("url")
            if url:
                return url
        return None

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

    def fetch_playlist_with_tracks(self, playlist_id: str) -> Optional[dict[str, Any]]:
        try:
            playlist = self.client.playlist(playlist_id)
        except Exception as exc:
            logger.warning("Unable to fetch playlist {}: {}", playlist_id, exc)
            return None

        tracks: List[dict[str, Any]] = []
        track_items = playlist.get("tracks") or {}
        position = 1

        def accumulate(items: List[dict[str, Any]]) -> None:
            nonlocal position
            for item in items:
                track = item.get("track")
                if not track:
                    continue
                track_id = track.get("id") or f"legacy-{playlist_id}-{position}"
                album = track.get("album") or {}
                artists = ", ".join(artist.get("name", "") for artist in track.get("artists", []))
                spotify_url = track.get("external_urls", {}).get("spotify")
                tracks.append(
                    {
                        "spotify_track_id": track_id,
                        "name": track.get("name", ""),
                        "artists": artists,
                        "album": album.get("name"),
                        "duration_ms": track.get("duration_ms"),
                        "position": position,
                        "spotify_url": spotify_url,
                        "artwork_url": self.pick_image_url(album.get("images")),
                    }
                )
                position += 1

        accumulate(track_items.get("items", []))
        while track_items.get("next"):
            try:
                track_items = self.client.next(track_items)
            except Exception as exc:
                logger.warning("Unable to paginate playlist {}: {}", playlist_id, exc)
                break
            accumulate(track_items.get("items", []))

        return {
            "id": playlist.get("id", playlist_id),
            "name": playlist.get("name", ""),
            "description": playlist.get("description", ""),
            "tracks": tracks,
            "snapshot_id": playlist.get("snapshot_id"),
        }

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
        logger.info("Adding {} tracks to Spotify playlist {}", len(track_list), playlist_id)
        self.client.playlist_add_items(playlist_id, track_list)
