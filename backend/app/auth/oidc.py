"""Generic OpenID Connect authorization-code + PKCE client."""

from __future__ import annotations

import base64
import hashlib
import hmac
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx
from authlib.jose import JsonWebKey, jwt  # type: ignore[import-untyped]

from app.core.config import Settings


class OidcError(Exception):
    """An OIDC provider response or token could not be trusted."""


@dataclass(frozen=True)
class OidcIdentity:
    subject: str
    issuer: str
    email: str | None
    email_verified: bool
    display_name: str | None
    session_id: str | None
    id_token: str


class OidcClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def authorization_url(self, state: str, nonce: str, code_verifier: str) -> str:
        metadata = await self._metadata()
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode("ascii")).digest())
            .rstrip(b"=")
            .decode("ascii")
        )
        query = urlencode(
            {
                "response_type": "code",
                "client_id": self.settings.oidc_client_id,
                "redirect_uri": str(self.settings.oidc_redirect_uri),
                "scope": "openid profile email",
                "state": state,
                "nonce": nonce,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }
        )
        return f"{metadata['authorization_endpoint']}?{query}"

    async def complete_login(self, code: str, code_verifier: str, nonce: str) -> OidcIdentity:
        metadata = await self._metadata()
        token_response = await self._token_response(metadata, code, code_verifier)
        id_token = token_response.get("id_token")
        if not isinstance(id_token, str):
            raise OidcError("provider token response did not include an ID token")

        claims = await self._validate_id_token(metadata, id_token, nonce)
        subject = claims.get("sub")
        if not isinstance(subject, str) or not subject:
            raise OidcError("ID token did not contain a subject")
        email = claims.get("email")
        return OidcIdentity(
            subject=subject,
            issuer=str(claims["iss"]),
            email=email if isinstance(email, str) else None,
            email_verified=claims.get("email_verified") is True,
            display_name=_display_name(claims),
            session_id=claims.get("sid") if isinstance(claims.get("sid"), str) else None,
            id_token=id_token,
        )

    async def logout_url(self, id_token_hint: str | None) -> str:
        metadata = await self._metadata()
        fallback = str(self.settings.oidc_post_logout_redirect_url or self.settings.app_base_url)
        endpoint = metadata.get("end_session_endpoint")
        if not isinstance(endpoint, str):
            return fallback
        query: dict[str, str] = {"post_logout_redirect_uri": fallback}
        if id_token_hint:
            query["id_token_hint"] = id_token_hint
        if self.settings.oidc_client_id:
            query["client_id"] = self.settings.oidc_client_id
        return f"{endpoint}?{urlencode(query)}"

    async def _metadata(self) -> dict[str, Any]:
        issuer = str(self.settings.oidc_issuer_url).rstrip("/")
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{issuer}/.well-known/openid-configuration")
            response.raise_for_status()
        metadata = response.json()
        if not isinstance(metadata, dict) or not isinstance(
            metadata.get("authorization_endpoint"), str
        ):
            raise OidcError("provider discovery document is incomplete")
        return metadata

    async def _token_response(
        self, metadata: dict[str, Any], code: str, code_verifier: str
    ) -> dict[str, Any]:
        endpoint = metadata.get("token_endpoint")
        if not isinstance(endpoint, str):
            raise OidcError("provider discovery document has no token endpoint")
        client_secret = self.settings.oidc_client_secret
        if not client_secret or not self.settings.oidc_client_id:
            raise OidcError("OIDC is not configured")
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                endpoint,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": str(self.settings.oidc_redirect_uri),
                    "code_verifier": code_verifier,
                },
                auth=(self.settings.oidc_client_id, client_secret.get_secret_value()),
            )
            response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise OidcError("provider token response was not an object")
        return payload

    async def _validate_id_token(
        self, metadata: dict[str, Any], id_token: str, nonce: str
    ) -> dict[str, Any]:
        jwks_uri = metadata.get("jwks_uri")
        if not isinstance(jwks_uri, str):
            raise OidcError("provider discovery document has no JWKS URI")
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(jwks_uri)
            response.raise_for_status()
        key_set = JsonWebKey.import_key_set(response.json())
        try:
            claims = jwt.decode(id_token, key_set)
            claims.validate(leeway=60)
        except Exception as error:
            raise OidcError("ID token signature or standard claims validation failed") from error

        expected_issuer = str(self.settings.oidc_issuer_url).rstrip("/")
        audience = claims.get("aud")
        audiences = audience if isinstance(audience, list) else [audience]
        if (
            not hmac.compare_digest(str(claims.get("iss", "")).rstrip("/"), expected_issuer)
            or self.settings.oidc_client_id not in audiences
            or not hmac.compare_digest(str(claims.get("nonce", "")), nonce)
        ):
            raise OidcError("ID token issuer, audience, or nonce validation failed")
        return dict(claims)


def _display_name(claims: dict[str, Any]) -> str | None:
    for name in ("name", "preferred_username", "email"):
        value = claims.get(name)
        if isinstance(value, str) and value:
            return value
    return None
