"""Deadline reminders and round-lifecycle notifications."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Round, RoundMember, Series, Submission, Track, User
from app.services import notifications


def _settings(**overrides: object) -> notifications.Settings:
    defaults: dict[str, object] = {
        "smtp_host": None,
        "smtp_from_address": None,
        "mattermost_webhook_url": None,
    }
    defaults.update(overrides)
    return notifications.Settings(**defaults)


def _configured_email_settings() -> notifications.Settings:
    return _settings(smtp_host="smtp.example.com", smtp_from_address="rounds@example.com")


def test_start_due_reminders_claims_each_window_exactly_once(
    db: Session, make_series: Callable[..., Series], make_round: Callable[..., Round]
) -> None:
    now = datetime.now(UTC)
    series = make_series()
    round_ = make_round(series, closes_at=now + timedelta(hours=40))
    db.commit()

    first_pass = notifications.start_due_reminders(db, now=now)
    db.commit()

    assert first_pass == [(round_.id, "48h")]
    db.expire_all()
    refreshed = db.get(Round, round_.id)
    assert refreshed is not None
    assert refreshed.reminder_48h_sent_at == now
    assert refreshed.reminder_24h_sent_at is None

    # Calling again immediately must not re-claim the same window.
    assert notifications.start_due_reminders(db, now=now + timedelta(minutes=1)) == []


def test_start_due_reminders_claims_both_windows_after_a_long_downtime(
    db: Session, make_series: Callable[..., Series], make_round: Callable[..., Round]
) -> None:
    now = datetime.now(UTC)
    series = make_series()
    # Nothing checked in for a while - the round is now only 20 hours from
    # closing, so both thresholds have already been crossed.
    make_round(series, closes_at=now + timedelta(hours=20))
    db.commit()

    claimed = notifications.start_due_reminders(db, now=now)

    assert {window for _, window in claimed} == {"48h", "24h"}


def test_start_due_reminders_ignores_rounds_outside_any_window(
    db: Session, make_series: Callable[..., Series], make_round: Callable[..., Round]
) -> None:
    now = datetime.now(UTC)
    series = make_series()
    make_round(series, closes_at=now + timedelta(hours=72))
    db.commit()

    assert notifications.start_due_reminders(db, now=now) == []


def test_send_round_reminder_skips_declined_and_over_limit_members(
    db: Session,
    make_series: Callable[..., Series],
    make_round: Callable[..., Round],
    make_user: Callable[..., User],
    make_track: Callable[..., Track],
    make_submission: Callable[..., Submission],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    series = make_series()
    eligible = make_user(name="Eligible", email="eligible@example.com")
    declined = make_user(name="Declined", email="declined@example.com")
    maxed_out = make_user(name="MaxedOut", email="maxed@example.com")
    opted_out = make_user(name="OptedOut", email="opted-out@example.com")
    no_email = make_user(name="NoEmail", email=None)
    round_ = make_round(
        series, submission_limit=1, members=[eligible, declined, maxed_out, opted_out, no_email]
    )
    declined_membership = db.scalar(
        select(RoundMember).where(
            RoundMember.round_id == round_.id, RoundMember.user_id == declined.id
        )
    )
    assert declined_membership is not None
    declined_membership.declined_further_submissions_at = datetime.now(UTC)
    opted_out.notify_reminder_emails = False
    make_submission(round_, maxed_out, make_track())
    db.commit()

    monkeypatch.setattr(notifications, "get_settings", _configured_email_settings)
    sent_to: list[str] = []
    monkeypatch.setattr(
        notifications.email,
        "send_email",
        lambda _settings, to_address, _subject, _body: sent_to.append(to_address),
    )

    notifications.send_round_reminder(db, round_.id, "24h")

    assert sent_to == ["eligible@example.com"]


def test_notify_round_published_emails_members_and_posts_mattermost(
    db: Session,
    make_series: Callable[..., Series],
    make_round: Callable[..., Round],
    make_user: Callable[..., User],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    series = make_series()
    subscribed = make_user(name="Subscribed", email="subscribed@example.com")
    unsubscribed = make_user(name="Unsubscribed", email="unsubscribed@example.com")
    unsubscribed.notify_round_published_emails = False
    round_ = make_round(series, members=[subscribed, unsubscribed])
    db.commit()

    monkeypatch.setattr(
        notifications,
        "get_settings",
        lambda: _settings(
            smtp_host="smtp.example.com",
            smtp_from_address="rounds@example.com",
            mattermost_webhook_url="https://mattermost.example.com/hooks/token",
        ),
    )
    sent_to: list[str] = []
    posted: list[str] = []
    monkeypatch.setattr(
        notifications.email,
        "send_email",
        lambda _settings, to_address, _subject, _body: sent_to.append(to_address),
    )
    monkeypatch.setattr(
        notifications.mattermost, "post_message", lambda _settings, text: posted.append(text)
    )

    notifications.notify_round_published(db, round_.id)

    assert sent_to == ["subscribed@example.com"]
    assert len(posted) == 1
    assert round_.title in posted[0]


def test_notify_round_opened_skips_mattermost_when_not_configured(
    db: Session,
    make_series: Callable[..., Series],
    make_round: Callable[..., Round],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    series = make_series()
    round_ = make_round(series)
    db.commit()

    monkeypatch.setattr(notifications, "get_settings", _settings)

    def unexpected(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("must not post when Mattermost is not configured")

    monkeypatch.setattr(notifications.mattermost, "post_message", unexpected)

    notifications.notify_round_opened(db, round_.id)


def test_notify_round_opened_posts_when_configured(
    db: Session,
    make_series: Callable[..., Series],
    make_round: Callable[..., Round],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    series = make_series()
    round_ = make_round(series)
    db.commit()

    monkeypatch.setattr(
        notifications,
        "get_settings",
        lambda: _settings(mattermost_webhook_url="https://mattermost.example.com/hooks/token"),
    )
    posted: list[str] = []
    monkeypatch.setattr(
        notifications.mattermost, "post_message", lambda _settings, text: posted.append(text)
    )

    notifications.notify_round_opened(db, round_.id)

    assert len(posted) == 1
    assert round_.title in posted[0]
