from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest

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
