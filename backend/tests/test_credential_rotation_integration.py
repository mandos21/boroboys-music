"""PostgreSQL-backed credential key-rotation coverage."""

from __future__ import annotations

import uuid

import pytest
from cryptography.fernet import InvalidToken
from sqlalchemy import select

from app.core.security import decrypt, encrypt
from app.db.models import ExternalAccount, ExternalCredential, ExternalProvider, PlatformRole, User
from app.db.session import get_session_factory
from app.services.credential_rotation import rotate_credentials


def test_rotation_reencrypts_only_the_requested_key_version() -> None:
    suffix = uuid.uuid4().hex[:12]
    old_key, new_key = "old-test-key", "new-test-key"
    old_version, new_version = f"old-{suffix}", f"new-{suffix}"
    with get_session_factory()() as db:
        user = User(
            oidc_issuer="https://issuer.test",
            oidc_subject=f"rotate-{suffix}",
            platform_role=PlatformRole.MEMBER,
        )
        db.add(user)
        db.flush()
        account = ExternalAccount(
            user_id=user.id,
            provider=ExternalProvider.LASTFM,
            provider_subject=f"rotate-{suffix}",
        )
        db.add(account)
        db.flush()
        credential = ExternalCredential(
            external_account_id=account.id,
            ciphertext=encrypt('{"session_key":"old"}', old_key),
            key_version=old_version,
        )
        db.add(credential)
        db.commit()

        assert (
            rotate_credentials(
                db,
                old_key=old_key,
                from_version=old_version,
                new_key=new_key,
                to_version=new_version,
            )
            == 1
        )
        db.commit()
        rotated = db.scalar(
            select(ExternalCredential).where(ExternalCredential.id == credential.id)
        )
        assert rotated is not None
        assert rotated.key_version == new_version
        assert decrypt(rotated.ciphertext, new_key) == '{"session_key":"old"}'
        with pytest.raises(InvalidToken):
            decrypt(rotated.ciphertext, old_key)


def test_rotation_rejects_a_noop_version_change() -> None:
    with get_session_factory()() as db, pytest.raises(ValueError, match="must differ"):
        rotate_credentials(
            db,
            old_key="key",
            from_version="v1",
            new_key="key",
            to_version="v1",
        )
