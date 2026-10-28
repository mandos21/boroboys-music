"""Explicit, one-off re-encryption for provider credentials and series webhooks."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import decrypt, encrypt
from app.db.models import ExternalCredential, Series


def rotate_credentials(
    db: Session,
    *,
    old_key: str,
    from_version: str,
    new_key: str,
    to_version: str,
) -> int:
    """Re-encrypt every credential at one version under the current key.

    Callers supply the former key out of band. Rows are locked so a provider-link
    callback cannot overwrite a credential midway through this operation.
    """
    if not from_version or not to_version:
        raise ValueError("credential key versions must be non-empty")
    if from_version == to_version:
        raise ValueError("source and destination credential key versions must differ")
    credentials = list(
        db.scalars(
            select(ExternalCredential)
            .where(ExternalCredential.key_version == from_version)
            .with_for_update()
        )
    )
    for credential in credentials:
        plaintext = decrypt(credential.ciphertext, old_key)
        credential.ciphertext = encrypt(plaintext, new_key)
        credential.key_version = to_version
    series_destinations = list(
        db.scalars(
            select(Series)
            .where(Series.mattermost_webhook_key_version == from_version)
            .with_for_update()
        )
    )
    for series in series_destinations:
        if series.mattermost_webhook_ciphertext:
            plaintext = decrypt(series.mattermost_webhook_ciphertext, old_key)
            series.mattermost_webhook_ciphertext = encrypt(plaintext, new_key)
            series.mattermost_webhook_key_version = to_version
    return len(credentials) + len(series_destinations)
