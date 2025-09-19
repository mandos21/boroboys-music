from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api import deps


def test_get_playlist_manager_with_lastfm(monkeypatch):
    spotify = object()
    captured = {}

    class DummySettings:
        lastfm_api_key = "key"
        lastfm_shared_secret = "secret"

    class DummyLastFMService:
        @classmethod
        def from_settings(cls):
            captured["lastfm"] = True
            return "lastfm-instance"

    class DummyPlaylistManager:
        def __init__(self, spotify_service, lastfm_service=None):
            self.spotify_service = spotify_service
            self.lastfm_service = lastfm_service

    monkeypatch.setattr(deps, "get_settings", lambda: DummySettings())
    monkeypatch.setattr(deps, "LastFMService", DummyLastFMService)
    monkeypatch.setattr(deps, "PlaylistManager", DummyPlaylistManager)

    manager = deps.get_playlist_manager(spotify)

    assert isinstance(manager, DummyPlaylistManager)
    assert manager.spotify_service is spotify
    assert manager.lastfm_service == "lastfm-instance"
    assert captured["lastfm"]


def test_get_playlist_manager_without_lastfm(monkeypatch):
    spotify = object()

    class DummySettings:
        lastfm_api_key = ""
        lastfm_shared_secret = ""

    class DummyPlaylistManager:
        def __init__(self, spotify_service, lastfm_service=None):
            self.spotify_service = spotify_service
            self.lastfm_service = lastfm_service

    monkeypatch.setattr(deps, "get_settings", lambda: DummySettings())
    monkeypatch.setattr(deps, "PlaylistManager", DummyPlaylistManager)

    manager = deps.get_playlist_manager(spotify)

    assert manager.lastfm_service is None


def test_get_db_raises_setup_required(monkeypatch):
    def raise_value_error():
        raise ValueError("missing settings")

    monkeypatch.setattr(deps, "get_session_factory", raise_value_error)

    with pytest.raises(deps.SetupRequired):
        next(deps.get_db())


def test_require_admin_rejects_non_admin():
    user = SimpleNamespace(role="member")

    with pytest.raises(HTTPException) as exc:
        deps.require_admin(user)

    assert exc.value.status_code == 403
    assert "Admin access required" in exc.value.detail
