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


def test_monthly_top_tracks_returns_usable_track_suggestions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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


class FakeTagsResponse:
    def __init__(self, tags: list[str]) -> None:
        self._tags = tags

    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        return {"toptags": {"tag": [{"name": name} for name in self._tags]}}


def test_genre_tags_returns_track_level_tags_without_an_artist_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    def fake_get(*_: object, **kwargs: object) -> FakeTagsResponse:
        calls.append(kwargs)
        return FakeTagsResponse(["dream pop", "shoegaze"])

    monkeypatch.setattr(lastfm.httpx, "get", fake_get)

    tags = lastfm.genre_tags(Settings(lastfm_api_key="api-key"), "An Artist", "A Track")

    assert tags == ["dream pop", "shoegaze"]
    assert len(calls) == 1
    assert calls[0]["params"]["method"] == "track.getTopTags"


def test_genre_tags_falls_back_to_artist_tags_when_the_track_has_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = iter([FakeTagsResponse([]), FakeTagsResponse(["indie rock"])])
    calls: list[dict[str, object]] = []

    def fake_get(*_: object, **kwargs: object) -> FakeTagsResponse:
        calls.append(kwargs)
        return next(responses)

    monkeypatch.setattr(lastfm.httpx, "get", fake_get)

    tags = lastfm.genre_tags(Settings(lastfm_api_key="api-key"), "An Artist", "A Track")

    assert tags == ["indie rock"]
    assert [call["params"]["method"] for call in calls] == [
        "track.getTopTags",
        "artist.getTopTags",
    ]


def test_genre_tags_requires_an_api_key() -> None:
    with pytest.raises(lastfm.LastfmError):
        lastfm.genre_tags(Settings(lastfm_api_key=None), "An Artist", "A Track")
