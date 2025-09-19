import pytest

from app.config import Settings


def _base_kwargs(**overrides):
    base = {
        "DATABASE_HOST": "db.local",
        "DATABASE_PORT": 5432,
        "DATABASE_NAME": "boroboys",
        "DATABASE_USER": "user",
        "DATABASE_PASSWORD": "pass",
        "SPOTIFY_CLIENT_ID": "cid",
        "SPOTIFY_CLIENT_SECRET": "secret",
        "SPOTIFY_REDIRECT_URI": "http://localhost",
        "LASTFM_API_KEY": "lk",
        "LASTFM_SHARED_SECRET": "ls",
        "SECRET_KEY": "super-secret",
    }
    base.update(overrides)
    return base


def _settings(**kwargs):
    return Settings(**kwargs)


def test_database_url_uses_legacy_if_present():
    settings = _settings(**_base_kwargs(DATABASE_URL="postgresql+psycopg://legacy"))

    assert settings.database_url == "postgresql+psycopg://legacy"


def test_database_url_composed_when_all_parts_present():
    settings = _settings(**_base_kwargs())

    assert (
        settings.database_url
        == "postgresql+psycopg://user:pass@db.local:5432/boroboys"
    )


@pytest.mark.parametrize(
    "missing_field, alias",
    [
        ("DATABASE_HOST", "DATABASE_HOST"),
        ("DATABASE_NAME", "DATABASE_NAME"),
        ("DATABASE_USER", "DATABASE_USER"),
        ("DATABASE_PASSWORD", "DATABASE_PASSWORD"),
    ],
)
def test_database_url_raises_when_parts_missing(missing_field, alias):
    kwargs = _base_kwargs()
    kwargs[missing_field] = None
    settings = _settings(**kwargs)

    with pytest.raises(ValueError) as exc:
        _ = settings.database_url

    assert alias in str(exc.value)
