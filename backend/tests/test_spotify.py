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


def test_artists_by_id_returns_only_artist_objects(monkeypatch: pytest.MonkeyPatch) -> None:
    observed: dict[str, object] = {}

    def fake_get(*_: object, **kwargs: object) -> FakeResponse:
        observed.update(kwargs)
        return FakeResponse({"artists": [{"id": "first"}, None, "not-an-artist"]})

    monkeypatch.setattr(spotify.httpx, "get", fake_get)

    assert spotify.artists_by_id("token", ["first", "second"]) == [{"id": "first"}]
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

    assert (
        spotify.client_credentials_token(
            Settings(spotify_client_id="client", spotify_client_secret="secret")
        )
        == "application-token"
    )
    assert observed["data"] == {"grant_type": "client_credentials"}
    assert observed["auth"] == ("client", "secret")


def test_profile_image_uses_the_first_spotify_image() -> None:
    assert _spotify_profile_image({"images": [{"url": "https://cdn.test/avatar.jpg"}]}) == (
        "https://cdn.test/avatar.jpg"
    )
    assert _spotify_profile_image({"images": []}) is None


def test_search_result_payload_tolerates_malformed_nested_fields() -> None:
    from app.api.routes.rounds.discovery import _search_result_payload

    payload = _search_result_payload(
        {
            "id": "track-1",
            "name": "Song",
            "artists": "not-a-list",
            "album": {"name": 7, "images": [None, "junk", {"url": "https://img/a.jpg"}]},
            "uri": 12,
            "explicit": "yes",
        }
    )

    assert payload == {
        "spotifyTrackId": "track-1",
        "name": "Song",
        "artist": "",
        "album": None,
        "spotifyUri": None,
        "artworkUrl": "https://img/a.jpg",
        "providerMetadata": {"explicit": False, "isPlayable": True},
    }


def test_token_expiry_is_brought_forward_by_the_refresh_margin() -> None:
    from datetime import UTC, datetime, timedelta

    before = datetime.now(UTC)
    expiry = spotify.token_expiry({"expires_in": 3600})
    after = datetime.now(UTC)

    assert expiry is not None
    assert before + timedelta(seconds=3600) - spotify.TOKEN_REFRESH_MARGIN <= expiry
    assert expiry <= after + timedelta(seconds=3600) - spotify.TOKEN_REFRESH_MARGIN
    assert spotify.token_expiry({"expires_in": "3600"}) is None


def test_playlist_and_user_ids_are_escaped_in_request_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    urls: list[str] = []

    def fake_post(url: str, **_: object) -> FakeResponse:
        urls.append(url)
        return FakeResponse({"id": "new-playlist"})

    def fake_delete(url: str, **_: object) -> FakeResponse:
        urls.append(url)
        return FakeResponse({})

    monkeypatch.setattr(spotify.httpx, "post", fake_post)
    monkeypatch.setattr(spotify.httpx, "delete", fake_delete)

    spotify.create_playlist("token", "user name/../x", "Round", "desc")
    spotify.add_items("token", "list?id=1", ["spotify:track:a"])
    spotify.delete_playlist("token", "list/../other")

    assert urls == [
        f"{spotify.SPOTIFY_API}/users/user%20name%2F..%2Fx/playlists",
        f"{spotify.SPOTIFY_API}/playlists/list%3Fid%3D1/items",
        f"{spotify.SPOTIFY_API}/playlists/list%2F..%2Fother/followers",
    ]


def test_import_requests_only_accept_base62_playlist_ids() -> None:
    from datetime import UTC, datetime, timedelta

    from pydantic import ValidationError

    from app.api.routes.admin import PlaylistImportRequest

    now = datetime.now(UTC)
    timeline = {
        "publisher_account_id": "00000000-0000-0000-0000-000000000000",
        "opens_at": now - timedelta(days=2),
        "closes_at": now - timedelta(days=1),
        "published_at": now,
    }
    assert PlaylistImportRequest(spotify_playlist_id="37i9dQZF1DX4sWSpwq3LiO", **timeline)
    with pytest.raises(ValidationError):
        PlaylistImportRequest(spotify_playlist_id="../users/me", **timeline)
