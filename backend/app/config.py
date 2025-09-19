"""Application configuration management using pydantic settings."""
from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables or .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        populate_by_name=True,
    )

    database_host: Optional[str] = Field(default="localhost", alias="DATABASE_HOST")
    database_port: int = Field(default=5432, alias="DATABASE_PORT")
    database_name: Optional[str] = Field(default=None, alias="DATABASE_NAME")
    database_user: Optional[str] = Field(default=None, alias="DATABASE_USER")
    database_password: Optional[str] = Field(default=None, alias="DATABASE_PASSWORD")
    database_url_legacy: Optional[str] = Field(default=None, alias="DATABASE_URL")

    spotify_client_id: str = Field(alias="SPOTIFY_CLIENT_ID")
    spotify_client_secret: str = Field(alias="SPOTIFY_CLIENT_SECRET")
    spotify_redirect_uri: str = Field(alias="SPOTIFY_REDIRECT_URI")
    spotify_scope: str = Field(
        default="playlist-modify-private playlist-read-private user-read-email",
        alias="SPOTIFY_SCOPE",
    )

    lastfm_api_key: str = Field(alias="LASTFM_API_KEY")
    lastfm_shared_secret: str = Field(alias="LASTFM_SHARED_SECRET")
    lastfm_username: Optional[str] = Field(default=None, alias="LASTFM_USERNAME")

    secret_key: str = Field(alias="SECRET_KEY")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    enable_scheduler: bool = Field(default=True, alias="ENABLE_SCHEDULER")

    frontend_redirect_url: str = Field(default="/", alias="FRONTEND_REDIRECT_URL")

    @property
    def database_url(self) -> str:
        if self.database_url_legacy:
            return self.database_url_legacy

        missing = [
            name
            for name, value in (
                ("DATABASE_HOST", self.database_host),
                ("DATABASE_NAME", self.database_name),
                ("DATABASE_USER", self.database_user),
                ("DATABASE_PASSWORD", self.database_password),
            )
            if value in (None, "")
        ]
        if missing:
            missing_values = ", ".join(missing)
            raise ValueError(f"Missing database settings: {missing_values}")

        return (
            f"postgresql+psycopg://{self.database_user}:{self.database_password}"
            f"@{self.database_host}:{self.database_port}/{self.database_name}"
        )


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""

    return Settings()  # type: ignore[call-arg]


def reset_settings_cache() -> None:
    """Clear the cached settings, forcing a reload on next access."""

    get_settings.cache_clear()
