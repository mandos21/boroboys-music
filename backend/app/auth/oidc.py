"""Generic OpenID Connect authorization-code + PKCE client.

Synchronous on purpose: the routes that use it run on FastAPI's thread pool
alongside the synchronous database session, so an asynchronous client would
only have moved the blocking database work onto the event loop.
"""

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
    claims: dict[str, Any]


class OidcClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def authorization_url(self, state: str, nonce: str, code_verifier: str) -> str:
        metadata = self._metadata()
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
                "scope": self.settings.oidc_scope_string,
                "state": state,
                "nonce": nonce,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }
        )
        return f"{metadata['authorization_endpoint']}?{query}"

    def complete_login(self, code: str, code_verifier: str, nonce: str) -> OidcIdentity:
        metadata = self._metadata()
        token_response = self._token_response(metadata, code, code_verifier)
        id_token = token_response.get("id_token")
        if not isinstance(id_token, str):
            raise OidcError("provider token response did not include an ID token")

        claims = self._validate_id_token(metadata, id_token, nonce)
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
            claims=claims,
        )

    def logout_url(self, id_token_hint: str | None) -> str:
        metadata = self._metadata()
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

    def _metadata(self) -> dict[str, Any]:
        issuer = str(self.settings.oidc_issuer_url).rstrip("/")
        with httpx.Client(timeout=10.0) as client:
            response = client.get(f"{issuer}/.well-known/openid-configuration")
            response.raise_for_status()
        metadata = response.json()
        if not isinstance(metadata, dict) or not isinstance(
            metadata.get("authorization_endpoint"), str
        ):
            raise OidcError("provider discovery document is incomplete")
        return metadata

    def _token_response(
        self, metadata: dict[str, Any], code: str, code_verifier: str
    ) -> dict[str, Any]:
        endpoint = metadata.get("token_endpoint")
        if not isinstance(endpoint, str):
            raise OidcError("provider discovery document has no token endpoint")
        client_secret = self.settings.oidc_client_secret
        if not client_secret or not self.settings.oidc_client_id:
            raise OidcError("OIDC is not configured")
        with httpx.Client(timeout=10.0) as client:
            response = client.post(
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

    def _validate_id_token(
        self, metadata: dict[str, Any], id_token: str, nonce: str
    ) -> dict[str, Any]:
        jwks_uri = metadata.get("jwks_uri")
        if not isinstance(jwks_uri, str):
            raise OidcError("provider discovery document has no JWKS URI")
        with httpx.Client(timeout=10.0) as client:
            response = client.get(jwks_uri)
            response.raise_for_status()
        key_set = JsonWebKey.import_key_set(response.json())
        try:
            claims = jwt.decode(id_token, key_set)
            claims.validate(leeway=60)
        except Exception as error:
            raise OidcError("ID token signature or standard claims validation failed") from error

        if not _claims_match_provider(self.settings, claims, nonce):
            raise OidcError("ID token issuer, audience, or nonce validation failed")
        return dict(claims)


def _claims_match_provider(settings: Settings, claims: dict[str, Any], nonce: str) -> bool:
    expected_issuer = str(settings.oidc_issuer_url).rstrip("/")
    expected_client_id = settings.oidc_client_id or ""
    audience = claims.get("aud")
    audiences = audience if isinstance(audience, list) else [audience]
    if not all(isinstance(value, str) for value in audiences):
        return False
    return (
        hmac.compare_digest(str(claims.get("iss", "")).rstrip("/"), expected_issuer)
        and expected_client_id in audiences
        and (
            len(audiences) == 1
            or hmac.compare_digest(str(claims.get("azp") or ""), expected_client_id)
        )
        and hmac.compare_digest(str(claims.get("nonce", "")), nonce)
    )


def _display_name(claims: dict[str, Any]) -> str | None:
    for name in ("name", "preferred_username", "email"):
        value = claims.get(name)
        if isinstance(value, str) and value:
            return value
    return None
