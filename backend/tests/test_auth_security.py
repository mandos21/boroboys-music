from fastapi.testclient import TestClient

from app.api.routes import auth
from app.core.config import Settings
from app.core.security import decrypt, encrypt, hash_secret, new_secret, secrets_match
from app.main import app


def test_opaque_secrets_are_random_hashable_and_encryptable() -> None:
    first, second = new_secret(), new_secret()

    assert first != second
    assert secrets_match(first, hash_secret(first))
    assert not secrets_match(second, hash_secret(first))
    assert decrypt(encrypt(first, "test-key"), "test-key") == first


def test_login_reports_disabled_oidc_without_touching_the_database(monkeypatch: object) -> None:
    monkeypatch.setattr(auth, "get_settings", lambda: Settings())  # type: ignore[attr-defined]

    response = TestClient(app).get("/api/v1/auth/login", follow_redirects=False)

    assert response.status_code == 503
    assert response.json()["detail"] == "OIDC is not configured"


def test_return_path_must_stay_within_the_frontend() -> None:
    assert auth._is_safe_return_path("/rounds?series=rock")
    assert not auth._is_safe_return_path("https://attacker.example")
    assert not auth._is_safe_return_path("//attacker.example")


def test_configured_oidc_admin_claim_accepts_list_and_rejects_other_values() -> None:
    settings = Settings(oidc_admin_claim="roles", oidc_admin_values="music-admin,operator")

    assert auth._is_claim_admin(settings, {"roles": ["member", "music-admin"]})
    assert not auth._is_claim_admin(settings, {"roles": "member"})
