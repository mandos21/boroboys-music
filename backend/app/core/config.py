from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, HttpUrl, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Deployment configuration; secrets are supplied outside version control."""

    model_config = SettingsConfigDict(env_file="../.env", extra="ignore")

    app_env: Literal["development", "test", "production"] = "development"
    app_name: str = Field(default="BoroCrew Music", min_length=1, max_length=100)
    app_base_url: HttpUrl = HttpUrl("http://localhost:5173")
    database_url: str = "postgresql+psycopg://music_rounds:music_rounds@localhost:5432/music_rounds"
    procrastinate_database_url: str = (
        "postgresql://music_rounds:music_rounds@localhost:5432/music_rounds"
    )
    credential_encryption_key: SecretStr = SecretStr("development-only-change-me")
    credential_encryption_key_version: str = "v1"
    oidc_issuer_url: HttpUrl | None = None
    oidc_client_id: str | None = None
    oidc_client_secret: SecretStr | None = None
    oidc_redirect_uri: HttpUrl = HttpUrl("http://localhost:8000/api/v1/auth/callback")
    oidc_scopes: str = "openid profile email"
    oidc_auto_provision_users: bool = True
    oidc_bootstrap_first_user_admin: bool = True
    oidc_require_verified_email: bool = False
    oidc_post_logout_redirect_url: HttpUrl | None = None
    oidc_bootstrap_admin_subjects: str = ""
    oidc_admin_claim: str | None = None
    oidc_admin_values: str = ""
    session_cookie_name: str = Field(
        default="music_rounds_session", pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,63}$"
    )
    session_lifetime_hours: int = Field(default=168, ge=1, le=24 * 365)
    lastfm_api_key: SecretStr | None = None
    lastfm_shared_secret: SecretStr | None = None
    lastfm_callback_url: HttpUrl = HttpUrl(
        "http://localhost:8000/api/v1/connections/lastfm/callback"
    )
    lastfm_evidence_refresh_hours: int = 24
    spotify_client_id: str | None = None
    spotify_client_secret: SecretStr | None = None
    spotify_redirect_uri: HttpUrl = HttpUrl(
        "http://127.0.0.1:8000/api/v1/connections/spotify/callback"
    )
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_from_address: str | None = None
    smtp_use_tls: bool = True
    mattermost_webhook_url: SecretStr | None = None

    @property
    def spotify_is_configured(self) -> bool:
        return all((self.spotify_client_id, self.spotify_client_secret))

    @property
    def lastfm_is_configured(self) -> bool:
        return all((self.lastfm_api_key, self.lastfm_shared_secret))

    @property
    def smtp_is_configured(self) -> bool:
        return all((self.smtp_host, self.smtp_from_address))

    @property
    def mattermost_is_configured(self) -> bool:
        return self.mattermost_webhook_url is not None

    @property
    def oidc_is_configured(self) -> bool:
        return all((self.oidc_issuer_url, self.oidc_client_id, self.oidc_client_secret))

    @property
    def bootstrap_admin_subjects(self) -> frozenset[str]:
        return frozenset(
            subject.strip()
            for subject in self.oidc_bootstrap_admin_subjects.split(",")
            if subject.strip()
        )

    @property
    def oidc_admin_claim_values(self) -> frozenset[str]:
        return frozenset(
            value.strip() for value in self.oidc_admin_values.split(",") if value.strip()
        )

    @property
    def oidc_scope_string(self) -> str:
        """Normalize configured scopes while preserving OpenID Connect's required scope."""
        scopes = [scope.strip() for scope in self.oidc_scopes.split() if scope.strip()]
        return " ".join(dict.fromkeys(("openid", *scopes)))

    @model_validator(mode="after")
    def production_secrets_are_not_defaults(self) -> Settings:
        if self.app_env != "production":
            return self
        insecure = {
            "CREDENTIAL_ENCRYPTION_KEY": self.credential_encryption_key.get_secret_value()
            == "development-only-change-me",
        }
        missing = [name for name, is_insecure in insecure.items() if is_insecure]
        if missing:
            raise ValueError(f"production requires non-default {', '.join(missing)}")
        if self.app_base_url.scheme != "https":
            raise ValueError("production APP_BASE_URL must use HTTPS")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
