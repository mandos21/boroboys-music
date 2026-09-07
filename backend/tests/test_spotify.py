from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest

from app.api.routes.connections import _spotify_profile_image
from app.core.config import Settings
from app.services import spotify


class FakeResponse:
    def __init__(self, payload: object) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        return self.payload


def test_authorization_url_uses_pkce_without_leaking_verifier() -> None:
    settings = Settings(spotify_client_id="client", spotify_client_secret="secret")

    url = spotify.authorization_url(settings, "state-value", "private-verifier")

    query = parse_qs(urlparse(url).query)
    assert query["state"] == ["state-value"]
    assert query["code_challenge_method"] == ["S256"]
    assert "private-verifier" not in url
    assert query["scope"] == [spotify.SCOPES]


def test_search_normalizes_only_spotify_track_items(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_get(*_: object, **__: object) -> FakeResponse:
        return FakeResponse({"tracks": {"items": [{"id": "track-1"}, "not-a-track"]}})

    monkeypatch.setattr(spotify.httpx, "get", fake_get)

    assert spotify.search_tracks("token", "song") == [{"id": "track-1"}]


def test_tracks_by_id_returns_only_track_objects(monkeypatch: pytest.MonkeyPatch) -> None:
    observed: dict[str, object] = {}

    def fake_get(*_: object, **kwargs: object) -> FakeResponse:
        observed.update(kwargs)
        return FakeResponse({"tracks": [{"id": "first"}, None, "not-a-track"]})

    monkeypatch.setattr(spotify.httpx, "get", fake_get)

    assert spotify.tracks_by_id("token", ["first", "second"]) == [{"id": "first"}]
    assert observed["params"] == {"ids": "first,second"}


def test_add_items_batches_at_spotify_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    batches: list[list[str]] = []

    def fake_post(*_: object, **kwargs: object) -> FakeResponse:
        payload = kwargs["json"]
        assert isinstance(payload, dict)
        batches.append(payload["uris"])
        return FakeResponse({})

    monkeypatch.setattr(spotify.httpx, "post", fake_post)

    spotify.add_items("token", "playlist", [f"spotify:track:{index}" for index in range(201)])

    assert [len(batch) for batch in batches] == [100, 100, 1]


def test_playlist_snapshot_pages_tracks_and_ignores_non_tracks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    def fake_get(url: str, **kwargs: object) -> FakeResponse:
        calls.append({"url": url, **kwargs})
        params = kwargs.get("params")
        if params is None:
            return FakeResponse({"name": "Archive"})
        assert isinstance(params, dict)
        if params["offset"] == 0:
            return FakeResponse(
                {
                    "items": [
                        {
                            "track": {
                                "type": "track",
                                "id": "first",
                                "name": "First",
                                "uri": "spotify:track:first",
                            }
                        },
                        {"track": {"type": "episode", "id": "episode"}},
                    ],
                    "next": "next-page",
                }
            )
        return FakeResponse(
            {
                "items": [
                    {
                        "track": {
                            "type": "track",
                            "id": "second",
                            "name": "Second",
                            "uri": "spotify:track:second",
                        }
                    }
                ],
                "next": None,
            }
        )

    monkeypatch.setattr(spotify.httpx, "get", fake_get)

    snapshot = spotify.playlist_snapshot("token", "archive-id")

    assert snapshot["name"] == "Archive"
    assert [track["id"] for track in snapshot["items"]] == ["first", "second"]
    assert [call.get("params", {}).get("offset") for call in calls[1:]] == [0, 2]


def test_refresh_token_uses_confidential_client_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    observed: dict[str, object] = {}

    def fake_post(*_: object, **kwargs: object) -> FakeResponse:
        observed.update(kwargs)
        return FakeResponse({"access_token": "refreshed", "expires_in": 3600})

    monkeypatch.setattr(spotify.httpx, "post", fake_post)
    settings = Settings(spotify_client_id="client", spotify_client_secret="secret")

    payload = spotify.refresh_token(settings, "refresh-value")

    assert payload["access_token"] == "refreshed"
    assert observed["auth"] == ("client", "secret")


def test_client_credentials_token_uses_application_grant(monkeypatch: pytest.MonkeyPatch) -> None:
    observed: dict[str, object] = {}

    def fake_post(*_: object, **kwargs: object) -> FakeResponse:
        observed.update(kwargs)
        return FakeResponse({"access_token": "application-token"})

    monkeypatch.setattr(spotify.httpx, "post", fake_post)

    assert spotify.client_credentials_token(Settings(spotify_client_id="client", spotify_client_secret="secret")) == "application-token"
    assert observed["data"] == {"grant_type": "client_credentials"}
    assert observed["auth"] == ("client", "secret")


def test_profile_image_uses_the_first_spotify_image() -> None:
    assert _spotify_profile_image({"images": [{"url": "https://cdn.test/avatar.jpg"}]}) == (
        "https://cdn.test/avatar.jpg"
    )
    assert _spotify_profile_image({"images": []}) is None
