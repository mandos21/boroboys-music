import asyncio

import pytest

from app.api.routes import auth
from app.auth.oidc import _claims_match_provider
from app.core.config import Settings
from app.core.security import decrypt, encrypt, hash_secret, new_secret, secrets_match
from app.db.models import PlatformRole


def test_opaque_secrets_are_random_hashable_and_encryptable() -> None:
    first, second = new_secret(), new_secret()

    assert first != second
    assert secrets_match(first, hash_secret(first))
    assert not secrets_match(second, hash_secret(first))
    assert decrypt(encrypt(first, "test-key"), "test-key") == first


def test_login_redirects_disabled_oidc_to_a_recoverable_ui_without_touching_database(
    monkeypatch: object,
) -> None:
    settings = Settings(
        oidc_issuer_url=None,
        oidc_client_id=None,
        oidc_client_secret=None,
    )
    monkeypatch.setattr(auth, "get_settings", lambda: settings)  # type: ignore[attr-defined]

    # The disabled branch must return before it needs a database session.
    response = asyncio.run(auth.login(db=None))  # type: ignore[arg-type]

    assert response.status_code == 303
    assert response.headers["location"] == "http://localhost:5173/auth/error?reason=oidc-unavailable"


def test_return_path_must_stay_within_the_frontend() -> None:
    assert auth._is_safe_return_path("/rounds?series=rock")
    assert not auth._is_safe_return_path("https://attacker.example")
    assert not auth._is_safe_return_path("//attacker.example")


def test_configured_oidc_admin_claim_accepts_list_and_rejects_other_values() -> None:
    settings = Settings(oidc_admin_claim="roles", oidc_admin_values="music-admin,operator")

    assert auth._is_claim_admin(settings, {"roles": ["member", "music-admin"]})
    assert not auth._is_claim_admin(settings, {"roles": "member"})


def test_first_provisioned_user_becomes_admin_without_provider_role_mapping() -> None:
    settings = Settings()

    assert (
        auth._provisioned_platform_role(settings, "first-user", {}, existing_user=False)
        is PlatformRole.ADMIN
    )
    assert (
        auth._provisioned_platform_role(settings, "later-user", {}, existing_user=True)
        is PlatformRole.MEMBER
    )


def test_first_user_bootstrap_can_be_disabled_without_disabling_claim_mapping() -> None:
    settings = Settings(
        oidc_bootstrap_first_user_admin=False,
        oidc_admin_claim="roles",
        oidc_admin_values="music-admin",
    )

    assert (
        auth._provisioned_platform_role(settings, "first-user", {}, existing_user=False)
        is PlatformRole.MEMBER
    )
    assert (
        auth._provisioned_platform_role(
            settings, "role-admin", {"roles": ["music-admin"]}, existing_user=True
        )
        is PlatformRole.ADMIN
    )


def test_oidc_scopes_preserve_openid_and_remove_duplicates() -> None:
    assert Settings(oidc_scopes="email openid profile email").oidc_scope_string == "openid email profile"


def test_multi_audience_id_tokens_require_this_client_as_the_authorized_party() -> None:
    settings = Settings(
        oidc_issuer_url="https://issuer.example/realms/music",
        oidc_client_id="music-rounds",
    )
    claims = {
        "iss": "https://issuer.example/realms/music",
        "aud": ["music-rounds", "another-client"],
        "nonce": "expected-nonce",
    }

    assert not _claims_match_provider(settings, claims, "expected-nonce")
    assert _claims_match_provider(settings, {**claims, "azp": "music-rounds"}, "expected-nonce")


def test_production_configuration_rejects_default_credential_key() -> None:
    with pytest.raises(ValueError, match="CREDENTIAL_ENCRYPTION_KEY"):
        Settings(
            app_env="production",
            app_base_url="https://music.example.test",
            credential_encryption_key="development-only-change-me",
        )

    production = Settings(
        app_env="production",
        app_base_url="https://music.example.test",
        credential_encryption_key="credential-key",
    )
    assert production.app_env == "production"
