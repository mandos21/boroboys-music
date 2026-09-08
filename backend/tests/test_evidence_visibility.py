"""The listening-evidence visibility ladder a listener chooses for themselves."""

from __future__ import annotations

import uuid

import pytest

from app.api.routes.rounds import _may_see_evidence
from app.db.models import EvidenceVisibility, ExternalAccount, ExternalProvider, PlatformRole, User

OWNER_ID = uuid.uuid4()


def _account(visibility: EvidenceVisibility) -> ExternalAccount:
    return ExternalAccount(
        user_id=OWNER_ID,
        provider=ExternalProvider.LASTFM,
        provider_subject="listener",
        evidence_visibility=visibility,
    )


def _viewer(user_id: uuid.UUID) -> User:
    return User(
        id=user_id,
        oidc_issuer="https://issuer.test",
        oidc_subject="viewer",
        platform_role=PlatformRole.MEMBER,
    )


@pytest.mark.parametrize(
    ("visibility", "is_member", "is_series_admin", "expected"),
    [
        # Shared with round members: also visible to the more privileged admin.
        (EvidenceVisibility.ROUND_MEMBERS, True, False, True),
        (EvidenceVisibility.ROUND_MEMBERS, False, True, True),
        (EvidenceVisibility.ROUND_MEMBERS, True, True, True),
        (EvidenceVisibility.ROUND_MEMBERS, False, False, False),
        # Narrowed to administrators: a plain round member must not see it.
        (EvidenceVisibility.SERIES_ADMINS, True, False, False),
        (EvidenceVisibility.SERIES_ADMINS, False, True, True),
        # Private is private from everyone but its owner.
        (EvidenceVisibility.PRIVATE, True, True, False),
    ],
)
def test_visibility_ladder_never_hides_more_from_a_more_privileged_viewer(
    visibility: EvidenceVisibility,
    is_member: bool,
    is_series_admin: bool,
    expected: bool,
) -> None:
    assert (
        _may_see_evidence(
            _account(visibility),
            _viewer(uuid.uuid4()),
            is_member=is_member,
            is_series_admin=is_series_admin,
        )
        is expected
    )


@pytest.mark.parametrize("visibility", list(EvidenceVisibility))
def test_a_listener_always_sees_their_own_evidence(visibility: EvidenceVisibility) -> None:
    assert (
        _may_see_evidence(
            _account(visibility), _viewer(OWNER_ID), is_member=False, is_series_admin=False
        )
        is True
    )
