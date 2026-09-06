"""Re-encrypt stored provider credentials under the configured active key."""

from __future__ import annotations

import argparse
import os
import sys

from app.core.config import get_settings
from app.db.session import get_session_factory
from app.services.credential_rotation import rotate_credentials


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-version", required=True, help="stored key version to replace")
    parser.add_argument(
        "--old-key-env",
        default="OLD_CREDENTIAL_ENCRYPTION_KEY",
        help="environment variable containing the former key",
    )
    args = parser.parse_args()
    old_key = os.environ.get(args.old_key_env)
    if not old_key:
        parser.error(f"{args.old_key_env} must contain the former credential encryption key")
    settings = get_settings()
    with get_session_factory()() as db:
        count = rotate_credentials(
            db,
            old_key=old_key,
            from_version=args.from_version,
            new_key=settings.credential_encryption_key.get_secret_value(),
            to_version=settings.credential_encryption_key_version,
        )
        db.commit()
    print(f"Rotated {count} credential record(s) to {settings.credential_encryption_key_version}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
