"""Personal per-series email settings preserve global opt-outs and series access."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.api.routes.profiles import (
    NotificationSettingsUpdate,
    get_series_notification_settings,
    update_series_notification_settings,
)
from app.core.config import get_settings
from app.core.security import hash_secret
from app.db.models import (
    ContributorGroup,
    ContributorGroupMember,
    RoundMember,
    SeriesAdmin,
    SeriesNotificationPreference,
    ServerSession,
)
from app.db.session import get_db_session
from app.main import create_app


def test_defaults_partial_updates_and_global_precedence(db, make_user, make_series, make_round):
    user = make_user()
    series = make_series()
    make_round(series, members=[user])
    first = get_series_notification_settings(db, user)[0]
    assert first["notifyReminderEmails"] is True
    assert first["effectiveReminderEmails"] is True
    assert db.scalar(select(func.count()).select_from(SeriesNotificationPreference)) == 0
    update_series_notification_settings(
        series.id, NotificationSettingsUpdate(notify_reminder_emails=False), db, user
    )
    saved = update_series_notification_settings(
        series.id, NotificationSettingsUpdate(notify_round_published_emails=False), db, user
    )
    assert saved["notifyReminderEmails"] is False
    assert saved["notifyRoundPublishedEmails"] is False
    user.notify_reminder_emails = False
    restored = update_series_notification_settings(
        series.id, NotificationSettingsUpdate(notify_reminder_emails=True), db, user
    )
    assert restored["notifyReminderEmails"] is True
    assert restored["effectiveReminderEmails"] is False
    assert restored["notifyRoundPublishedEmails"] is False
    assert db.scalar(select(func.count()).select_from(SeriesNotificationPreference)) == 1
    # Empty/null partial updates do not reset existing choices.
    assert (
        update_series_notification_settings(
            series.id, NotificationSettingsUpdate(notify_reminder_emails=None), db, user
        )
        == restored
    )


def test_visibility_matches_series_access_without_duplicates(
    db, make_user, make_series, make_round
):
    user = make_user()
    owned, grouped, historical, removed, private = [make_series() for _ in range(5)]
    db.add(SeriesAdmin(series_id=owned.id, user_id=user.id))
    group = ContributorGroup(series_id=grouped.id, name="Members")
    db.add(group)
    db.flush()
    db.add(ContributorGroupMember(group_id=group.id, user_id=user.id))
    make_round(owned, members=[user])
    make_round(historical, members=[user])
    make_round(historical, members=[user])
    old_round = make_round(removed, members=[user])
    membership = db.scalar(select(RoundMember).where(RoundMember.round_id == old_round.id))
    membership.removed_at = datetime.now(UTC)
    db.flush()
    rows = get_series_notification_settings(db, user)
    assert len(rows) == 3
    assert {row["seriesId"] for row in rows} == {str(s.id) for s in (owned, grouped, historical)}
    # Admin visibility alone never causes emails: recipient eligibility still needs RoundMember.
    admin = make_user(admin=True)
    assert len(get_series_notification_settings(db, admin)) == 5


def test_preferences_survive_rounds_and_rejoining_and_are_personal(
    db, make_user, make_series, make_round
):
    user, other = make_user(), make_user()
    series = make_series()
    round_ = make_round(series, members=[user, other])
    update_series_notification_settings(
        series.id, NotificationSettingsUpdate(notify_reminder_emails=False), db, user
    )
    membership = db.scalar(
        select(RoundMember).where(RoundMember.round_id == round_.id, RoundMember.user_id == user.id)
    )
    membership.removed_at = datetime.now(UTC)
    db.flush()
    assert get_series_notification_settings(db, user) == []
    make_round(series, members=[user])
    assert get_series_notification_settings(db, user)[0]["notifyReminderEmails"] is False
    assert get_series_notification_settings(db, other)[0]["notifyReminderEmails"] is True


def test_http_auth_csrf_access_and_contract(db, make_user, make_series, make_round):
    user = make_user()
    series, private = make_series(), make_series()
    make_round(series, members=[user])
    db.add(
        ServerSession(
            user_id=user.id,
            token_hash=hash_secret("preferences-session"),
            csrf_secret_hash=hash_secret("preferences-csrf"),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
    )
    db.commit()
    app = create_app()
    app.dependency_overrides[get_db_session] = lambda: db
    path = "/api/v1/profiles/me/notification-settings/series"
    with TestClient(app) as client:
        assert client.get(path).status_code == 401
        assert client.patch(f"{path}/{series.id}", json={}).status_code == 401
        client.cookies.set(get_settings().session_cookie_name, "preferences-session")
        response = client.get(path)
        assert response.status_code == 200
        assert response.json()[0]["seriesId"] == str(series.id)
        assert client.patch(f"{path}/{series.id}", json={}).status_code == 403
        client.headers["X-CSRF-Token"] = "preferences-csrf"
        assert client.patch(f"{path}/{private.id}", json={}).status_code == 404
        response = client.patch(f"{path}/{series.id}", json={"notify_reminder_emails": False})
        assert response.status_code == 200
        assert response.json()["effectiveReminderEmails"] is False
        assert response.json()["effectiveRoundPublishedEmails"] is True
        assert (
            client.patch(f"{path}/{series.id}", json={"notify_reminder_emails": []}).status_code
            == 422
        )
        assert client.patch(f"{path}/invalid", json={}).status_code == 422


@pytest.mark.parametrize("category", ["notify_reminder_emails", "notify_round_published_emails"])
def test_missing_preference_does_not_override_global_opt_out(
    db, make_user, make_series, make_round, category
):
    user = make_user()
    setattr(user, category, False)
    make_round(make_series(), members=[user])
    result = get_series_notification_settings(db, user)[0]
    assert (
        result[
            "effectiveReminderEmails"
            if category == "notify_reminder_emails"
            else "effectiveRoundPublishedEmails"
        ]
        is False
    )
