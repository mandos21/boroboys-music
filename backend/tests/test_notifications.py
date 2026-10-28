"""Notification timing, recipient safety, retries, and series administration."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import func, select

from app.api.routes.admin import notifications as routes
from app.core.config import Settings
from app.core.security import decrypt
from app.db.models import (
    NotificationDelivery,
    NotificationEvent,
    NotificationRule,
    Publication,
    PublicationState,
    RoundMember,
    RoundStatus,
    SeriesAdmin,
)
from app.services import notification_rules as service
from app.services.credential_rotation import rotate_credentials


@pytest.fixture
def settings(monkeypatch):
    value = Settings(
        smtp_host="smtp.test",
        smtp_from_address="music@example.test",
        mattermost_webhook_url="https://chat.example.test/hooks/test",
    )
    monkeypatch.setattr(service, "get_settings", lambda: value)
    monkeypatch.setattr(routes, "get_settings", lambda: value)
    return value


@pytest.fixture
def sent(monkeypatch, settings):
    calls = []
    monkeypatch.setattr(
        service.email,
        "send_email",
        lambda _settings, address, subject, body: calls.append((address, body)),
    )
    monkeypatch.setattr(
        service.mattermost,
        "post_message",
        lambda _settings, message, **kwargs: calls.append(("mattermost", message)),
    )
    return calls


@pytest.fixture
def make_rule(db):
    def make(series, **kwargs):
        values = dict(
            name="Reminder",
            enabled=True,
            channel="email",
            milestone="closes",
            offset_minutes=-1440,
            audience="remaining",
            message_template="{round_title} closes {closes_at}: {round_url}",
        )
        active_since = kwargs.pop("active_since", datetime.now(UTC) - timedelta(days=100))
        values.update(kwargs)
        rule = NotificationRule(
            series_id=series.id,
            active_since=active_since,
            **service.RuleInput.model_validate(values).model_dump(),
        )
        db.add(rule)
        db.flush()
        return rule

    return make


def test_claim_once_and_recover_missing_enqueue(
    db, make_series, make_round, make_user, make_rule, sent
):
    now = datetime.now(UTC)
    series = make_series()
    user = make_user(email="one@example.test")
    round_ = make_round(series, members=[user], closes_at=now + timedelta(hours=23))
    make_rule(series)
    first = service.collect_due(db, now)
    db.commit()
    assert len(first) == 1
    assert service.collect_due(db, now) == first
    assert db.scalar(select(func.count()).select_from(NotificationEvent)) == 1
    service.deliver(db, first[0], now)
    service.deliver(db, first[0], now)
    assert len(sent) == 1 and round_.title in sent[0][1]
    assert service.collect_due(db, now) == []


def test_recipient_capacity_preferences_and_declined_rechecked(
    db, make_series, make_round, make_user, make_track, make_submission, make_rule, sent
):
    now = datetime.now(UTC)
    series = make_series()
    users = [make_user(name=str(i), email=f"{i}@example.test") for i in range(7)]
    round_ = make_round(
        series, submission_limit=1, members=users, closes_at=now + timedelta(hours=23)
    )
    make_submission(round_, users[1], make_track())
    members = {
        m.user_id: m
        for m in db.scalars(select(RoundMember).where(RoundMember.round_id == round_.id))
    }
    members[users[2].id].declined_further_submissions_at = now
    members[users[3].id].removed_at = now
    users[4].notify_reminder_emails = False
    users[5].is_active = False
    members[users[0].id].submission_limit_override = 2
    make_submission(round_, users[0], make_track())
    make_rule(series)
    db.flush()
    ids = service.collect_due(db, now)
    assert len(ids) == 2
    users[6].notify_reminder_emails = False
    db.commit()
    for id_ in ids:
        service.deliver(db, id_, now)
    assert [address for address, _ in sent] == ["0@example.test"]
    assert sorted(db.scalars(select(NotificationDelivery.status))) == ["sent", "skipped"]


def test_partial_failure_retries_only_failed_recipient(
    db, make_series, make_round, make_user, make_rule, monkeypatch, sent
):
    now = datetime.now(UTC)
    series = make_series()
    make_round(
        series,
        members=[make_user(email="ok@test.com"), make_user(email="retry@test.com")],
        closes_at=now + timedelta(hours=23),
    )
    make_rule(series)
    ids = service.collect_due(db, now)
    attempts = []

    def send(_settings, address, _subject, _body):
        attempts.append(address)
        if address == "retry@test.com" and attempts.count(address) == 1:
            raise service.email.EmailError("private provider details")

    monkeypatch.setattr(service.email, "send_email", send)
    for id_ in ids:
        service.deliver(db, id_, now)
    assert service.collect_due(db, now + timedelta(minutes=1)) == []
    retries = service.collect_due(db, now + timedelta(minutes=3))
    assert len(retries) == 1
    service.deliver(db, retries[0], now + timedelta(minutes=3))
    assert attempts.count("ok@test.com") == 1
    assert attempts.count("retry@test.com") == 2
    assert all(d.status == "sent" for d in db.scalars(select(NotificationDelivery)))


def test_failure_is_bounded_and_redacted(
    db, make_series, make_round, make_user, make_rule, monkeypatch, sent
):
    now = datetime.now(UTC)
    series = make_series()
    make_round(
        series, members=[make_user(email="member@test.com")], closes_at=now + timedelta(hours=23)
    )
    make_rule(series)

    def fail(*args):
        raise service.email.EmailError("secret webhook token")

    monkeypatch.setattr(service.email, "send_email", fail)
    [id_] = service.collect_due(db, now)
    for _ in range(5):
        service.deliver(db, id_, now)
        delivery = db.get(NotificationDelivery, id_)
        now = delivery.next_attempt_at
    assert delivery.status == "failed" and delivery.attempt_count == 5
    assert "secret" not in delivery.last_error
    assert service.collect_due(db, now) == []


def test_reschedule_disable_and_message_edit(
    db, make_series, make_round, make_user, make_rule, sent
):
    now = datetime.now(UTC)
    series = make_series()
    round_ = make_round(
        series, members=[make_user(email="one@test.com")], closes_at=now + timedelta(hours=23)
    )
    rule = make_rule(series)
    [id_] = service.collect_due(db, now)
    round_.closes_at += timedelta(days=2)
    round_.publish_at += timedelta(days=2)
    rule.message_template = "Updated {round_title}"
    db.commit()
    service.deliver(db, id_, now)
    assert not sent
    due = db.get(NotificationDelivery, id_).next_attempt_at
    service.deliver(db, id_, due)
    assert sent[0][1].startswith("Updated ")
    round_.closes_at += timedelta(days=1)
    round_.publish_at += timedelta(days=1)
    db.commit()
    assert service.collect_due(db, due + timedelta(days=1)) == []


@pytest.mark.parametrize("change", ["disabled", "deleted", "archived", "cancelled"])
def test_pending_delivery_respects_current_state(
    change, db, make_series, make_round, make_user, make_rule, sent
):
    now = datetime.now(UTC)
    series = make_series()
    round_ = make_round(
        series, members=[make_user(email="one@test.com")], closes_at=now + timedelta(hours=23)
    )
    rule = make_rule(series)
    [id_] = service.collect_due(db, now)
    if change == "disabled":
        rule.enabled = False
    elif change == "deleted":
        rule.is_deleted = True
    elif change == "archived":
        series.is_archived = True
    else:
        round_.status = RoundStatus.CANCELLED
    db.commit()
    service.deliver(db, id_, now)
    assert not sent
    assert db.get(NotificationDelivery, id_).status == "skipped"


def test_new_rules_do_not_backfill_and_short_round_reminders_wait_for_opening(
    db, make_series, make_round, make_rule, sent
):
    now = datetime.now(UTC)
    series = make_series()
    make_round(series, opens_at=now - timedelta(days=2), closes_at=now + timedelta(hours=23))
    make_rule(series, channel="mattermost", audience="members", active_since=now)
    assert service.collect_due(db, now) == []
    future = make_round(
        series,
        status=RoundStatus.SCHEDULED,
        opens_at=now + timedelta(hours=2),
        closes_at=now + timedelta(hours=8),
    )
    rule = make_rule(series)
    assert service.scheduled_at(rule, future, None) == future.opens_at


def test_unconfigured_channel_is_recorded_and_not_backfilled(
    db, make_series, make_round, make_rule, monkeypatch, sent
):
    now = datetime.now(UTC)
    series = make_series(use_shared_mattermost=False)
    make_round(series, closes_at=now + timedelta(hours=23))
    make_rule(series, channel="mattermost", audience="members")
    assert service.collect_due(db, now) == []
    db.flush()
    event = db.scalar(select(NotificationEvent))
    assert "not configured" in event.skip_reason
    series.use_shared_mattermost = True
    db.commit()
    assert service.collect_due(db, now) == []


def test_actual_publication_not_planned_time_and_imports_are_skipped(
    db, make_series, make_round, make_rule, make_user, make_spotify_account, sent
):
    now = datetime.now(UTC)
    series = make_series()
    round_ = make_round(
        series,
        status=RoundStatus.CLOSED,
        opens_at=now - timedelta(days=80),
        closes_at=now - timedelta(days=70),
        publish_at=now - timedelta(days=69),
    )
    make_rule(
        series,
        channel="mattermost",
        audience="members",
        milestone="published",
        offset_minutes=60,
        active_since=now - timedelta(days=1),
    )
    assert service.collect_due(db, now) == []
    account = make_spotify_account(make_user())
    publication = Publication(
        round_id=round_.id,
        publisher_account_id=account.id,
        idempotency_key=str(uuid.uuid4()),
        state=PublicationState.PUBLISHED,
        published_at=now,
    )
    round_.status = RoundStatus.PUBLISHED
    db.add(publication)
    db.flush()
    assert service.collect_due(db, now) == []
    [id_] = service.collect_due(db, now + timedelta(hours=1))
    service.deliver(db, id_, now + timedelta(hours=1))
    assert len(sent) == 1
    publication.is_imported = True
    other_rule = make_rule(
        series, channel="mattermost", audience="members", milestone="published", offset_minutes=0
    )
    db.commit()
    assert not service.relevant(other_rule, round_, publication, now)


@pytest.mark.parametrize(
    "message",
    ["{unknown}", "{round_title.__class__}", "{round_title!r}", "{round_title:>10}", "{", " "],
)
def test_invalid_templates_rejected(message):
    with pytest.raises(ValidationError):
        service.RuleInput(
            name="Rule", channel="mattermost", milestone="opens", message_template=message
        )


def test_publication_before_and_invalid_audience_rejected():
    with pytest.raises(ValidationError):
        service.RuleInput(
            name="Rule",
            channel="mattermost",
            milestone="published",
            offset_minutes=-1,
            message_template="Hello",
        )
    with pytest.raises(ValidationError):
        service.RuleInput(
            name="Rule",
            channel="email",
            milestone="published",
            audience="remaining",
            message_template="Hello",
        )


def test_channel_and_rules_require_series_admin_and_never_expose_webhook(
    db, make_series, make_user, settings
):
    series = make_series()
    admin = make_user()
    outsider = make_user()
    db.add(SeriesAdmin(series_id=series.id, user_id=admin.id))
    db.flush()
    url = "https://chat.example.test/hooks/secret-token"
    payload = routes.ChannelUpdate(mode="custom", webhook_url=url)
    with pytest.raises(HTTPException) as denied:
        routes.update_channel(series.id, payload, db, outsider)
    assert denied.value.status_code == 403
    routes.update_channel(series.id, payload, db, admin)
    assert (
        decrypt(
            series.mattermost_webhook_ciphertext,
            settings.credential_encryption_key.get_secret_value(),
        )
        == url
    )
    view = routes.get_notifications(series.id, db, admin)
    assert view.channels.mattermostMode == "custom" and view.channels.mattermostReady
    assert "secret-token" not in view.model_dump_json()
    assert (
        rotate_credentials(
            db,
            old_key=settings.credential_encryption_key.get_secret_value(),
            from_version=settings.credential_encryption_key_version,
            new_key="new-test-key",
            to_version="v2",
        )
        == 1
    )
    assert decrypt(series.mattermost_webhook_ciphertext, "new-test-key") == url


def test_crud_preview_timezone_isolation_and_history(
    db, make_series, make_user, make_round, settings, sent
):
    series = make_series()
    series.timezone = "America/New_York"
    admin = make_user(admin=True)
    round_ = make_round(series, closes_at=datetime(2027, 1, 3, 17, tzinfo=UTC))
    other_round = make_round(make_series())
    rule = routes.create_rule(
        series.id,
        service.RuleInput(
            name="Opening",
            channel="mattermost",
            milestone="opens",
            message_template="{series_name}: {closes_at}",
        ),
        db,
        admin,
    )
    preview = routes.preview_rule(
        series.id,
        routes.PreviewInput(
            round_id=round_.id, **service.RuleInput.model_validate(rule.__dict__).model_dump()
        ),
        db,
        admin,
    )
    assert "12:00 PM EST" in preview.message
    assert not sent
    with pytest.raises(HTTPException) as missing:
        routes.preview_rule(
            series.id,
            routes.PreviewInput(
                round_id=other_round.id,
                **service.RuleInput.model_validate(rule.__dict__).model_dump(),
            ),
            db,
            admin,
        )
    assert missing.value.status_code == 404
    original_since = rule.active_since
    routes.update_rule(
        series.id,
        rule.id,
        service.RuleInput(
            name="New text", channel="mattermost", milestone="opens", message_template="Updated"
        ),
        db,
        admin,
    )
    assert rule.active_since == original_since
    routes.delete_rule(series.id, rule.id, db, admin)
    assert routes.get_notifications(series.id, db, admin).rules == []


@pytest.mark.parametrize(
    "url",
    [
        "http://chat.test/hooks/token",
        "https://user:pass@chat.test/hooks/token",
        "https://chat.test/api/delete",
        "https://chat.test/hooks/token?secret=yes",
    ],
)
def test_webhooks_must_be_https_incoming_webhooks(url):
    with pytest.raises(ValidationError):
        routes.ChannelUpdate(mode="custom", webhook_url=url)


def test_moving_a_pending_round_earlier_recalculates_the_queue(
    db, make_series, make_round, make_user, make_rule, sent
):
    now = datetime.now(UTC)
    series = make_series()
    round_ = make_round(
        series, members=[make_user(email="one@test.com")], closes_at=now + timedelta(hours=23)
    )
    make_rule(series)
    [id_] = service.collect_due(db, now)
    round_.closes_at += timedelta(days=5)
    round_.publish_at += timedelta(days=5)
    db.commit()
    service.deliver(db, id_, now)
    assert db.get(NotificationDelivery, id_).next_attempt_at > now
    round_.closes_at = now + timedelta(hours=23)
    db.commit()
    assert service.collect_due(db, now) == [id_]
    service.deliver(db, id_, now)
    assert len(sent) == 1


def test_default_rules_announce_new_successor_once(db, make_series, make_round, make_rule, sent):
    from app.services.lifecycle import create_successor

    now = datetime.now(UTC)
    series = make_series(auto_start=True, round_plan={"kind": "rolling", "duration_days": 7})
    make_rule(series, channel="mattermost", audience="members", milestone="opens", offset_minutes=0)
    published = make_round(
        series,
        status=RoundStatus.PUBLISHED,
        opens_at=now - timedelta(days=14),
        closes_at=now - timedelta(days=7),
    )
    successor = create_successor(db, published, now=now)
    db.commit()
    [id_] = service.collect_due(db, now)
    service.deliver(db, id_, now)
    assert successor.title in sent[0][1]
    assert service.collect_due(db, now) == []


def test_concurrent_collectors_and_delivery_workers_send_once(engine, settings, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from sqlalchemy.orm import Session

    from app.db.models import Round, Series

    now = datetime.now(UTC)
    with Session(engine) as setup:
        series = Series(name="Concurrent", slug="concurrent", timezone="UTC")
        setup.add(series)
        setup.flush()
        round_ = Round(
            series_id=series.id,
            title="Concurrent round",
            timezone="UTC",
            submission_limit=3,
            opens_at=now - timedelta(days=1),
            closes_at=now + timedelta(hours=23),
            publish_at=now + timedelta(days=1),
            status=RoundStatus.OPEN,
        )
        rule = NotificationRule(
            series_id=series.id,
            name="Concurrent rule",
            channel="mattermost",
            milestone="closes",
            offset_minutes=-1440,
            audience="members",
            message_template="Hello",
            active_since=now - timedelta(days=3),
        )
        setup.add_all([round_, rule])
        setup.commit()
    barrier = Barrier(2)

    def collect():
        with Session(engine) as session:
            barrier.wait(timeout=5)
            ids = service.collect_due(session, now)
            session.commit()
            return ids

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: collect(), range(2)))
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(NotificationEvent)) == 1
        [delivery_id] = list(session.scalars(select(NotificationDelivery.id)))
    calls = []
    monkeypatch.setattr(
        service.mattermost, "post_message", lambda *args, **kwargs: calls.append("sent")
    )
    barrier = Barrier(2)

    def send():
        with Session(engine) as session:
            barrier.wait(timeout=5)
            service.deliver(session, delivery_id, now)

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: send(), range(2)))
    assert calls == ["sent"]


def test_http_contract_uses_real_auth_csrf_and_validates_templates(
    db, make_series, make_user, make_round, settings
):
    from fastapi.testclient import TestClient

    from app.core.security import hash_secret
    from app.db.models import ServerSession
    from app.db.session import get_db_session
    from app.main import create_app

    admin = make_user(admin=True)
    series = make_series()
    round_ = make_round(series)
    db.add(
        ServerSession(
            user_id=admin.id,
            token_hash=hash_secret("test-session"),
            csrf_secret_hash=hash_secret("test-csrf"),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
    )
    db.commit()
    app = create_app()
    app.dependency_overrides[get_db_session] = lambda: db
    client = TestClient(app)
    path = f"/api/v1/admin/series/{series.id}/notifications"
    assert client.get(path).status_code == 401
    client.cookies.set(settings.session_cookie_name, "test-session")
    payload = dict(
        name="HTTP rule",
        channel="email",
        milestone="closes",
        offset_minutes=-60,
        audience="remaining",
        message_template="{round_title}: {round_url}",
    )
    assert client.post(path + "/rules", json=payload).status_code == 403
    client.headers["X-CSRF-Token"] = "test-csrf"
    created = client.post(path + "/rules", json=payload)
    assert created.status_code == 201, created.text
    rule_id = created.json()["id"]
    assert client.get(path).json()["rules"][0]["id"] == rule_id
    assert (
        client.post(path + "/preview", json={**payload, "round_id": str(round_.id)}).status_code
        == 200
    )
    invalid = client.put(
        path + f"/rules/{rule_id}", json={**payload, "message_template": "{unsupported}"}
    )
    assert invalid.status_code == 422
    assert client.delete(path + f"/rules/{rule_id}").status_code == 204
    assert client.get(path).json()["rules"] == []
