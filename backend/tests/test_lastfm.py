from __future__ import annotations

import pytest

from app.core.config import Settings
from app.services import lastfm


class FakeResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        return {
            "toptracks": {
                "track": [
                    {"name": "A Track", "artist": {"name": "An Artist"}},
                    {"name": "No artist"},
                ]
            }
        }


def test_monthly_top_tracks_returns_usable_track_suggestions(monkeypatch: pytest.MonkeyPatch) -> None:
    observed: dict[str, object] = {}

    def fake_get(*_: object, **kwargs: object) -> FakeResponse:
        observed.update(kwargs)
        return FakeResponse()

    monkeypatch.setattr(lastfm.httpx, "get", fake_get)

    tracks = lastfm.monthly_top_tracks(Settings(lastfm_api_key="api-key"), "listener", limit=4)

    assert tracks == [{"name": "A Track", "artist": "An Artist", "artworkUrl": None}]
    assert observed["params"] == {
        "method": "user.getTopTracks",
        "api_key": "api-key",
        "user": "listener",
        "period": "1month",
        "limit": 4,
        "format": "json",
    }
