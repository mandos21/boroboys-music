"""PostgreSQL-backed administration read-side authorization coverage."""

from __future__ import annotations

import uuid

from app.api.routes.admin import (
    get_series_for_administration,
    list_series_for_administration,
    search_users_for_series,
)
from app.db.models import (
    ContributorGroup,
    ContributorGroupMember,
    PlatformRole,
    Series,
    SeriesAdmin,
    User,
)
from app.db.session import get_session_factory


def test_series_admin_reads_only_assigned_series_and_searches_active_users() -> None:
    suffix = uuid.uuid4().hex[:12]
    with get_session_factory()() as db:
        series_admin = User(
            oidc_issuer="https://issuer.test",
            oidc_subject=f"series-admin-{suffix}",
            display_name="Series Admin",
            platform_role=PlatformRole.MEMBER,
        )
        member = User(
            oidc_issuer="https://issuer.test",
            oidc_subject=f"member-{suffix}",
            email=f"member-{suffix}@example.test",
            display_name="Matched Member",
            platform_role=PlatformRole.MEMBER,
        )
        assigned = Series(
            name=f"Assigned {suffix}",
            slug=f"assigned-{suffix}",
            timezone="UTC",
            default_policies=[],
        )
        other = Series(
            name=f"Other {suffix}",
            slug=f"other-{suffix}",
            timezone="UTC",
            default_policies=[],
        )
        db.add_all((series_admin, member, assigned, other))
        db.flush()
        group = ContributorGroup(series_id=assigned.id, name="Contributors")
        db.add_all(
            (
                SeriesAdmin(series_id=assigned.id, user_id=series_admin.id),
                group,
            )
        )
        db.flush()
        db.add(ContributorGroupMember(group_id=group.id, user_id=member.id))
        db.commit()

        visible = list_series_for_administration(db, series_admin)
        assert [item["id"] for item in visible] == [str(assigned.id)]
        detail = get_series_for_administration(assigned.id, db, series_admin)
        assert detail["groups"] == [
            {
                "id": str(group.id),
                "name": "Contributors",
                "description": None,
                "memberCount": 1,
                "members": [
                    {
                        "id": str(member.id),
                        "displayName": "Matched Member",
                        "email": member.email,
                    }
                ],
            }
        ]
        assert search_users_for_series(assigned.id, "Matched", db, series_admin) == [
            {
                "id": str(member.id),
                "displayName": "Matched Member",
                "email": member.email,
            }
        ]
