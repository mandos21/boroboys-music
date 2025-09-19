from __future__ import annotations

from pathlib import Path

import pytest

from app.services import setup_service


@pytest.fixture(autouse=True)
def override_setup_flag(tmp_path, monkeypatch):
    flag = tmp_path / ".setup_unlocked"
    monkeypatch.setattr(setup_service, "SETUP_FLAG_PATH", flag)
    yield
    if flag.exists():
        flag.unlink()


def _minimal_config():
    return setup_service.assemble_setup_config(
        database_host="localhost",
        database_port=5432,
        database_name="boroboys",
        database_user="postgres",
        database_password="postgres",
        spotify_client_id="cid",
        spotify_client_secret="secret",
        spotify_redirect_uri="http://localhost/callback",
        spotify_scope="scope",
        secret_key="super-secret",
        admin_username="admin",
        admin_password="password123",
    )


def test_unlock_and_setup_flag():
    assert not setup_service.setup_unlocked()
    assert not setup_service.SETUP_FLAG_PATH.exists()

    assert setup_service.unlock_setup("boroboys-init")
    assert setup_service.setup_unlocked()
    assert setup_service.SETUP_FLAG_PATH.read_text() == "unlocked"

    setup_service.clear_setup_flag()
    assert not setup_service.setup_unlocked()


def test_assemble_setup_config_merges_defaults():
    config = _minimal_config()

    assert config["DATABASE_HOST"] == "localhost"
    assert config["FRONTEND_REDIRECT_URL"] == "http://localhost:5173/"
    assert config["ENABLE_SCHEDULER"] == "true"
    assert config["ADMIN_USERNAME"] == "admin"
    assert config["ADMIN_PASSWORD"] == "password123"


def test_initialize_application_writes_env_and_creates_admin(monkeypatch):
    env_written = {}
    db_urls = {}
    admin_calls = {}

    def fake_write_env_file(config, overwrite):
        env_written["config"] = config
        env_written["overwrite"] = overwrite
        return Path(".env")

    def fake_initialize_database(url):
        db_urls["url"] = url

    def fake_create_admin(**kwargs):
        admin_calls.update(kwargs)

    monkeypatch.setattr(setup_service, "write_env_file", fake_write_env_file)
    monkeypatch.setattr(setup_service, "initialize_database", fake_initialize_database)
    monkeypatch.setattr(setup_service, "create_or_update_admin_user", fake_create_admin)
    monkeypatch.setattr(setup_service, "hash_password", lambda value: f"hashed:{value}")
    monkeypatch.setattr(setup_service, "reset_settings_cache", lambda: None)

    config = _minimal_config()

    setup_service.initialize_application(config, overwrite_env=True)

    assert env_written["overwrite"] is True
    assert env_written["config"]["DATABASE_HOST"] == "localhost"
    assert "ADMIN_USERNAME" not in env_written["config"]

    assert db_urls["url"].startswith("postgresql+psycopg://")

    assert admin_calls["username"] == "admin"
    assert admin_calls["display_name"] == "admin"
    assert admin_calls["password_hash"] == "hashed:password123"
    assert admin_calls["spotify_user_id"] is None
    assert not setup_service.SETUP_FLAG_PATH.exists()


def test_initialize_application_rejects_existing_env(monkeypatch):
    def fake_write_env_file(config, overwrite):
        raise FileExistsError("exists")

    monkeypatch.setattr(setup_service, "write_env_file", fake_write_env_file)

    config = _minimal_config()

    with pytest.raises(FileExistsError):
        setup_service.initialize_application(config)
