"""Exercise the notification migration with existing series and claimed reminders."""

from __future__ import annotations

import uuid

from alembic import command
from alembic.config import Config
from sqlalchemy import text


def test_existing_series_receive_defaults_without_repeating_old_claims(engine):
    config = Config("alembic.ini")
    series_id, round_id = uuid.uuid4(), uuid.uuid4()
    command.downgrade(config, "800f9880f496")
    try:
        with engine.begin() as connection:
            connection.execute(
                text("""
                INSERT INTO series (id, name, slug, timezone, default_policies,
                                    auto_start_next_round, is_archived)
                VALUES (:id, 'Migration series', 'migration-series', 'UTC', '[]', false, false)
            """),
                {"id": series_id},
            )
            connection.execute(
                text("""
                INSERT INTO rounds (id, series_id, title, timezone, status, submission_limit,
                                    opens_at, closes_at, publish_at, policy_snapshot,
                                    opened_announced_at, reminder_24h_sent_at)
                VALUES (:id, :series, 'Existing round', 'UTC', 'OPEN', 3,
                        now() - interval '2 days', now() + interval '23 hours',
                        now() + interval '24 hours', '[]', now() - interval '2 days', now())
            """),
                {"id": round_id, "series": series_id},
            )
        command.upgrade(config, "head")
        with engine.connect() as connection:
            rules = list(
                connection.execute(
                    text("SELECT * FROM notification_rules WHERE series_id = :id"),
                    {"id": series_id},
                ).mappings()
            )
            assert len(rules) == 5
            assert all(rule["enabled"] and not rule["is_deleted"] for rule in rules)
            claims = list(
                connection.execute(
                    text("""
                SELECT n.milestone, n.offset_minutes FROM notification_events e
                JOIN notification_rules n ON e.rule_id = n.id WHERE e.round_id = :id
            """),
                    {"id": round_id},
                ).tuples()
            )
            assert set(claims) == {("opens", 0), ("closes", -1440)}
            assert (
                connection.scalar(
                    text("SELECT use_shared_mattermost FROM series WHERE id = :id"),
                    {"id": series_id},
                )
                is True
            )
    finally:
        command.upgrade(config, "head")
