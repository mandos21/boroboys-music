"""The OIDC client against a fake provider: caching and signature policy."""

from __future__ import annotations

import time
from typing import Any

import pytest
from authlib.jose import JsonWebKey, jwt  # type: ignore[import-untyped]
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.auth import oidc
from app.core.config import Settings

ISSUER = "https://issuer.example/realms/music"


class FakeResponse:
    def __init__(self, payload: object) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        return self.payload


class FakeProvider:
    """Serves discovery and JWKS, and counts how often each is fetched."""

    def __init__(self) -> None:
        self.fetches: dict[str, int] = {}
        self.rotate_keys()

    def rotate_keys(self) -> None:
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        pem = private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        self.key = JsonWebKey.import_key(pem, {"kty": "RSA", "kid": f"kid-{time.monotonic()}"})
        self.jwks = {"keys": [self.key.as_dict()]}

    def id_token(self, alg: str = "RS256", **claims: Any) -> str:
        now = int(time.time())
        payload = {
            "iss": ISSUER,
            "aud": "music-rounds",
            "sub": "person",
            "nonce": "nonce",
            "iat": now,
            "exp": now + 300,
            **claims,
        }
        header = {"alg": alg, "kid": self.key.as_dict()["kid"]}
        key = self.key if alg.startswith(("RS", "PS")) else self.key.as_dict()["n"]
        return jwt.encode(header, payload, key).decode("ascii")

    def get(self, url: str) -> FakeResponse:
        self.fetches[url] = self.fetches.get(url, 0) + 1
        if url.endswith("/.well-known/openid-configuration"):
            return FakeResponse(
                {
                    "authorization_endpoint": f"{ISSUER}/auth",
                    "token_endpoint": f"{ISSUER}/token",
                    "jwks_uri": f"{ISSUER}/jwks",
                    "id_token_signing_alg_values_supported": ["RS256", "HS256"],
                }
            )
        if url.endswith("/jwks"):
            return FakeResponse(self.jwks)
        raise AssertionError(f"unexpected fetch {url}")

    def __enter__(self) -> FakeProvider:
        return self

    def __exit__(self, *_: object) -> None:
        return None


@pytest.fixture
def provider(monkeypatch: pytest.MonkeyPatch) -> FakeProvider:
    fake = FakeProvider()
    monkeypatch.setattr(oidc.httpx, "Client", lambda **_: fake)
    oidc._documents.clear()
    return fake


@pytest.fixture
def client() -> oidc.OidcClient:
    return oidc.OidcClient(
        Settings(
            oidc_issuer_url=ISSUER,
            oidc_client_id="music-rounds",
            oidc_client_secret="secret",
        )
    )


def test_discovery_and_jwks_are_fetched_once_per_ttl(
    provider: FakeProvider, client: oidc.OidcClient
) -> None:
    metadata = client._metadata()
    for _ in range(3):
        claims = client._validate_id_token(metadata, provider.id_token(), "nonce")
        assert claims["sub"] == "person"

    assert provider.fetches == {
        f"{ISSUER}/.well-known/openid-configuration": 1,
        f"{ISSUER}/jwks": 1,
    }


def test_a_token_signed_with_a_symmetric_algorithm_is_rejected(
    provider: FakeProvider, client: oidc.OidcClient
) -> None:
    """The provider advertises HS256 too, but a JWKS-verified token must never use it."""
    metadata = client._metadata()

    with pytest.raises(oidc.OidcError):
        client._validate_id_token(metadata, provider.id_token(alg="HS256"), "nonce")


def test_a_key_rotation_inside_the_cache_window_is_recovered_with_one_refetch(
    provider: FakeProvider, client: oidc.OidcClient
) -> None:
    metadata = client._metadata()
    client._validate_id_token(metadata, provider.id_token(), "nonce")
    provider.rotate_keys()

    claims = client._validate_id_token(metadata, provider.id_token(), "nonce")

    assert claims["sub"] == "person"
    assert provider.fetches[f"{ISSUER}/jwks"] == 2
