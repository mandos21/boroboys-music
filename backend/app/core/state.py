from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from typing import Optional

SPOTIFY_TRACK_PATTERN = re.compile(
    r"(?:https?://open\.spotify\.com/track/|spotify:track:)?([A-Za-z0-9]{22})"
)

SPOTIFY_PLAYLIST_PATTERN = re.compile(
    r"(?:https?://open\.spotify\.com/playlist/|spotify:playlist:)?([A-Za-z0-9]{22})"
)


def generate_signed_state(secret_key: str) -> str:
    nonce = secrets.token_urlsafe(16)
    signature = hmac.new(secret_key.encode("utf-8"), nonce.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{nonce}.{signature}"


def validate_signed_state(state: Optional[str], secret_key: str) -> bool:
    if not state or "." not in state:
        return False
    nonce, signature = state.split(".", 1)
    expected_signature = hmac.new(
        secret_key.encode("utf-8"), nonce.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(signature, expected_signature)


def extract_track_identifier(raw_value: str) -> str:
    value = (raw_value or "").strip()
    match = SPOTIFY_TRACK_PATTERN.search(value)
    if match:
        return match.group(1)
    return value


def extract_playlist_identifier(raw_value: str) -> Optional[str]:
    value = (raw_value or "").strip()
    if not value:
        return None
    match = SPOTIFY_PLAYLIST_PATTERN.search(value)
    if match:
        return match.group(1)
    if len(value) == 22 and value.isalnum():
        return value
    return None
