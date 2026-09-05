"""Small, explicit primitives for opaque sessions and encrypted short-lived secrets."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

from cryptography.fernet import Fernet


def new_secret() -> str:
    return secrets.token_urlsafe(32)


def hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def secrets_match(value: str, expected_hash: str) -> bool:
    return hmac.compare_digest(hash_secret(value), expected_hash)


def encrypt(value: str, key_material: str) -> str:
    return _fernet(key_material).encrypt(value.encode("utf-8")).decode("ascii")


def decrypt(value: str, key_material: str) -> str:
    return _fernet(key_material).decrypt(value.encode("ascii")).decode("utf-8")


def _fernet(key_material: str) -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(key_material.encode("utf-8")).digest())
    return Fernet(key)
