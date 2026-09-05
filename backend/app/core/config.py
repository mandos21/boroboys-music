from __future__ import annotations

from functools import lru_cache

from pydantic import HttpUrl, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Deployment configuration; secrets are supplied outside version control."""

    model_config = SettingsConfigDict(env_file="../.env", extra="ignore")

    app_env: str = "development"
    app_base_url: HttpUrl = HttpUrl("http://localhost:5173")
    database_url: str = "postgresql+psycopg://music_rounds:music_rounds@localhost:5432/music_rounds"
    procrastinate_database_url: str = "postgresql://music_rounds:music_rounds@localhost:5432/music_rounds"
    session_secret: SecretStr = SecretStr("development-only-change-me")
    credential_encryption_key: SecretStr = SecretStr("development-only-change-me")
    oidc_issuer_url: HttpUrl | None = None
    oidc_client_id: str | None = None
    oidc_client_secret: SecretStr | None = None
    oidc_auto_provision_users: bool = True
    oidc_require_verified_email: bool = False
    oidc_post_logout_redirect_url: HttpUrl | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
