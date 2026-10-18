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


class FakeTrackInfoResponse:
    def __init__(self, payload: object) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        return self.payload


def test_track_listeners_uses_global_unique_listeners_not_user_playcount(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: dict[str, object] = {}

    def fake_get(*_: object, **kwargs: object) -> FakeTrackInfoResponse:
        observed.update(kwargs)
        return FakeTrackInfoResponse({"track": {"listeners": "123456", "playcount": "999999"}})

    monkeypatch.setattr(lastfm.httpx, "get", fake_get)
    assert lastfm.track_listeners(Settings(lastfm_api_key="api-key"), "Artist", "Song") == 123456
    assert observed["params"]["method"] == "track.getInfo"  # type: ignore[index]
    assert "username" not in observed["params"]  # type: ignore[operator]


def test_track_listeners_keeps_missing_and_failed_lookups_distinct(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(lastfm.httpx, "get", lambda *_, **__: FakeTrackInfoResponse({"error": 7}))
    assert lastfm.track_listeners(Settings(lastfm_api_key="api-key"), "Artist", "Song") is None
    monkeypatch.setattr(lastfm.httpx, "get", lambda *_, **__: FakeTrackInfoResponse({"error": 29}))
    with pytest.raises(lastfm.LastfmError):
        lastfm.track_listeners(Settings(lastfm_api_key="api-key"), "Artist", "Song")
    monkeypatch.setattr(lastfm.httpx, "get", lambda *_, **__: FakeTrackInfoResponse({"error": 6}))
    with pytest.raises(lastfm.LastfmError):
        lastfm.track_listeners(Settings(lastfm_api_key="api-key"), "Artist", "Song")


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


class FakeUserInfoResponse:
    def __init__(self, images: list[dict[str, str]] | None) -> None:
        self._images = images

    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        user: dict[str, object] = {"name": "listener"}
        if self._images is not None:
            user["image"] = self._images
        return {"user": user}


def test_user_profile_image_picks_the_largest_available_size(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: dict[str, object] = {}

    def fake_get(*_: object, **kwargs: object) -> FakeUserInfoResponse:
        observed.update(kwargs)
        return FakeUserInfoResponse(
            [
                {"size": "small", "#text": "https://lastfm.test/small.jpg"},
                {"size": "extralarge", "#text": "https://lastfm.test/large.jpg"},
            ]
        )

    monkeypatch.setattr(lastfm.httpx, "get", fake_get)

    image = lastfm.user_profile_image(Settings(lastfm_api_key="api-key"), "listener")

    assert image == "https://lastfm.test/large.jpg"
    assert observed["params"] == {
        "method": "user.getInfo",
        "api_key": "api-key",
        "user": "listener",
        "format": "json",
    }


def test_user_profile_image_returns_none_without_an_image(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(lastfm.httpx, "get", lambda *_, **__: FakeUserInfoResponse(None))

    assert lastfm.user_profile_image(Settings(lastfm_api_key="api-key"), "listener") is None


def test_user_profile_image_requires_an_api_key() -> None:
    with pytest.raises(lastfm.LastfmError):
        lastfm.user_profile_image(Settings(lastfm_api_key=None), "listener")
