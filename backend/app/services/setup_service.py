"""Helpers used to coordinate the initial application setup."""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from loguru import logger
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.bootstrap import (
    DEFAULT_CONFIG,
    build_database_url_from_config,
    create_or_update_admin_user,
    initialize_database,
    write_env_file,
)
from app.config import get_settings, reset_settings_cache
from app.security import hash_password

SETUP_PASSWORD = "boroboys-init"
SETUP_FLAG_PATH = Path(__file__).resolve().parents[2] / ".setup_unlocked"


def settings_ready() -> bool:
    try:
        get_settings()
        return True
    except (ValidationError, ValueError):
        return False


def unlock_setup(password: str) -> bool:
    if password == SETUP_PASSWORD:
        SETUP_FLAG_PATH.write_text("unlocked", encoding="utf-8")
        return True
    return False


def setup_unlocked() -> bool:
    return SETUP_FLAG_PATH.exists()


def clear_setup_flag() -> None:
    if SETUP_FLAG_PATH.exists():
        SETUP_FLAG_PATH.unlink()


def initialize_application(config: Dict[str, str], *, overwrite_env: bool = False) -> None:
    env_config = {key: value for key, value in config.items() if not key.startswith("ADMIN_")}
    admin_username = config["ADMIN_USERNAME"]
    admin_display_name = config["ADMIN_DISPLAY_NAME"]
    admin_password = config["ADMIN_PASSWORD"]
    admin_spotify_id = config.get("ADMIN_SPOTIFY_ID") or None
    admin_lastfm_username = config.get("ADMIN_LASTFM_USERNAME") or None

    database_url = build_database_url_from_config(env_config)

    try:
        write_env_file(env_config, overwrite=overwrite_env)
    except FileExistsError:
        logger.info(".env already exists and overwrite flag not set")
        raise

    try:
        initialize_database(database_url)
    except SQLAlchemyError as exc:
        logger.error("Database initialization failed: {}", exc)
        raise

    password_hash = hash_password(admin_password)
    create_or_update_admin_user(
        database_url=database_url,
        username=admin_username,
        display_name=admin_display_name,
        password_hash=password_hash,
        spotify_user_id=admin_spotify_id,
        lastfm_username=admin_lastfm_username,
    )
    reset_settings_cache()
    clear_setup_flag()


def assemble_setup_config(
    *,
    database_host: str,
    database_port: int,
    database_name: str,
    database_user: str,
    database_password: str,
    spotify_client_id: str,
    spotify_client_secret: str,
    spotify_redirect_uri: str,
    spotify_scope: str,
    secret_key: str,
    frontend_redirect_url: Optional[str] = None,
    log_level: Optional[str] = None,
    enable_scheduler: Optional[bool] = None,
    lastfm_api_key: Optional[str] = None,
    lastfm_shared_secret: Optional[str] = None,
    lastfm_username: Optional[str] = None,
    admin_username: str = "admin",
    admin_display_name: Optional[str] = None,
    admin_password: str = "",
    admin_spotify_id: Optional[str] = None,
    admin_lastfm_username: Optional[str] = None,
) -> Dict[str, str]:
    scheduler_value = (
        str(enable_scheduler).lower() if isinstance(enable_scheduler, bool) else None
    )

    config = DEFAULT_CONFIG.copy()
    config.update(
        {
            "DATABASE_HOST": database_host.strip(),
            "DATABASE_PORT": str(database_port),
            "DATABASE_NAME": database_name.strip(),
            "DATABASE_USER": database_user.strip(),
            "DATABASE_PASSWORD": database_password,
            "SECRET_KEY": secret_key.strip(),
            "FRONTEND_REDIRECT_URL": (frontend_redirect_url or config.get("FRONTEND_REDIRECT_URL", "http://localhost:5173/")).strip(),
            "SPOTIFY_CLIENT_ID": spotify_client_id.strip(),
            "SPOTIFY_CLIENT_SECRET": spotify_client_secret.strip(),
            "SPOTIFY_REDIRECT_URI": spotify_redirect_uri.strip(),
            "SPOTIFY_SCOPE": spotify_scope.strip(),
            "LASTFM_API_KEY": (lastfm_api_key or "").strip(),
            "LASTFM_SHARED_SECRET": (lastfm_shared_secret or "").strip(),
            "LASTFM_USERNAME": (lastfm_username or "").strip(),
            "LOG_LEVEL": (log_level or config["LOG_LEVEL"]).upper(),
            "ENABLE_SCHEDULER": scheduler_value if scheduler_value is not None else config["ENABLE_SCHEDULER"],
            "ADMIN_USERNAME": admin_username.strip(),
            "ADMIN_DISPLAY_NAME": (admin_display_name or admin_username).strip(),
            "ADMIN_PASSWORD": admin_password,
            "ADMIN_SPOTIFY_ID": (admin_spotify_id or "").strip(),
            "ADMIN_LASTFM_USERNAME": (admin_lastfm_username or "").strip(),
        }
    )
    return config
