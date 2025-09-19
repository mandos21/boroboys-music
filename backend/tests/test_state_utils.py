import re

from app.core.state import (
    extract_playlist_identifier,
    extract_track_identifier,
    generate_signed_state,
    validate_signed_state,
)


def test_generate_signed_state_roundtrip() -> None:
    secret = "super-secret-key"
    state = generate_signed_state(secret)
    assert validate_signed_state(state, secret)


def test_generate_signed_state_rejects_tampering() -> None:
    secret = "another-secret"
    state = generate_signed_state(secret)
    assert not validate_signed_state(state + "oops", secret)
    assert not validate_signed_state(None, secret)


def test_extract_track_identifier_from_url() -> None:
    raw_url = "https://open.spotify.com/track/0123456789abcdefghijkl"
    track_id = extract_track_identifier(raw_url)
    assert re.fullmatch(r"[A-Za-z0-9]{22}", track_id)


def test_extract_playlist_identifier_variants() -> None:
    playlist_id = "abcdefghijklmnopqrstuv"
    assert (
        extract_playlist_identifier(f"https://open.spotify.com/playlist/{playlist_id}")
        == playlist_id
    )
    assert extract_playlist_identifier(f"spotify:playlist:{playlist_id}") == playlist_id
    assert extract_playlist_identifier(playlist_id) == playlist_id
    assert extract_playlist_identifier("invalid-link") is None
