"""Application-owned persistence model for Music Rounds v2."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PlatformRole(str, enum.Enum):
    MEMBER = "member"
    ADMIN = "admin"


class ExternalProvider(str, enum.Enum):
    SPOTIFY = "spotify"
    LASTFM = "lastfm"


class EvidenceVisibility(str, enum.Enum):
    ROUND_MEMBERS = "round_members"
    SERIES_ADMINS = "series_admins"
    PRIVATE = "private"


class RoundStatus(str, enum.Enum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    OPEN = "open"
    CLOSED = "closed"
    PUBLISHING = "publishing"
    PUBLISHED = "published"
    UNPUBLISHING = "unpublishing"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SubmissionStatus(str, enum.Enum):
    ACCEPTED = "accepted"
    WITHDRAWN = "withdrawn"


class EvaluationDecision(str, enum.Enum):
    ACCEPT = "accept"
    WARN = "warn"
    REJECT = "reject"


class PublicationState(str, enum.Enum):
    PENDING = "pending"
    PUBLISHING = "publishing"
    PUBLISHED = "published"
    UNPUBLISHING = "unpublishing"
    UNPUBLISHED = "unpublished"
    FAILED = "failed"


class UUIDTimestampMixin:
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class User(UUIDTimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("oidc_issuer", "oidc_subject", name="uq_users_oidc_identity"),
    )

    oidc_issuer: Mapped[str] = mapped_column(String(500), nullable=False)
    oidc_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320))
    display_name: Mapped[str | None] = mapped_column(String(200))
    platform_role: Mapped[PlatformRole] = mapped_column(default=PlatformRole.MEMBER, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class ServerSession(UUIDTimestampMixin, Base):
    __tablename__ = "server_sessions"
    __table_args__ = (UniqueConstraint("token_hash", name="uq_server_sessions_token_hash"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    csrf_secret_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    oidc_session_id: Mapped[str | None] = mapped_column(String(255))
    oidc_id_token_ciphertext: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class OidcLoginAttempt(UUIDTimestampMixin, Base):
    __tablename__ = "oidc_login_attempts"
    __table_args__ = (UniqueConstraint("state_hash", name="uq_oidc_login_attempts_state_hash"),)

    state_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    nonce_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    nonce_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    code_verifier_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    return_path: Mapped[str] = mapped_column(String(2048), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ExternalAccount(UUIDTimestampMixin, Base):
    __tablename__ = "external_accounts"
    __table_args__ = (
        UniqueConstraint(
            "provider", "provider_subject", name="uq_external_accounts_provider_subject"
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[ExternalProvider] = mapped_column(nullable=False)
    provider_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(200))
    scopes: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    evidence_visibility: Mapped[EvidenceVisibility] = mapped_column(
        default=EvidenceVisibility.ROUND_MEMBERS, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    disconnected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ExternalCredential(UUIDTimestampMixin, Base):
    __tablename__ = "external_credentials"
    __table_args__ = (
        UniqueConstraint("external_account_id", name="uq_external_credentials_account"),
    )

    external_account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("external_accounts.id", ondelete="CASCADE"), nullable=False
    )
    ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    key_version: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Series(UUIDTimestampMixin, Base):
    __tablename__ = "series"
    __table_args__ = (UniqueConstraint("slug", name="uq_series_slug"),)

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    default_policies: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, nullable=False
    )
    round_plan: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    auto_start_next_round: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class SeriesAdmin(UUIDTimestampMixin, Base):
    __tablename__ = "series_admins"
    __table_args__ = (
        UniqueConstraint("series_id", "user_id", name="uq_series_admins_series_user"),
    )

    series_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("series.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )


class ContributorGroup(UUIDTimestampMixin, Base):
    __tablename__ = "contributor_groups"
    __table_args__ = (
        UniqueConstraint("series_id", "name", name="uq_contributor_groups_series_name"),
    )

    series_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("series.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)


class ContributorGroupMember(UUIDTimestampMixin, Base):
    __tablename__ = "contributor_group_members"
    __table_args__ = (UniqueConstraint("group_id", "user_id", name="uq_group_members_group_user"),)

    group_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("contributor_groups.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )


class Round(UUIDTimestampMixin, Base):
    __tablename__ = "rounds"
    __table_args__ = (
        CheckConstraint("opens_at < closes_at", name="ck_rounds_open_before_close"),
        CheckConstraint("closes_at <= publish_at", name="ck_rounds_close_before_publish"),
        CheckConstraint("submission_limit >= 0", name="ck_rounds_submission_limit_nonnegative"),
    )

    series_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("series.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    submission_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    opens_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    closes_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    publish_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    status: Mapped[RoundStatus] = mapped_column(
        default=RoundStatus.DRAFT, nullable=False, index=True
    )
    publisher_account_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("external_accounts.id")
    )
    policy_snapshot: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, nullable=False
    )
    published_sequence: Mapped[int | None] = mapped_column(Integer)


class RoundMember(UUIDTimestampMixin, Base):
    __tablename__ = "round_members"
    __table_args__ = (UniqueConstraint("round_id", "user_id", name="uq_round_members_round_user"),)

    round_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("rounds.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    submission_limit_override: Mapped[int | None] = mapped_column(Integer)
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Track(UUIDTimestampMixin, Base):
    __tablename__ = "tracks"
    __table_args__ = (UniqueConstraint("spotify_track_id", name="uq_tracks_spotify_track_id"),)

    spotify_track_id: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    artist: Mapped[str] = mapped_column(String(500), nullable=False)
    album: Mapped[str | None] = mapped_column(String(500))
    spotify_uri: Mapped[str | None] = mapped_column(String(128))
    artwork_url: Mapped[str | None] = mapped_column(String(1000))
    provider_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)


class Submission(UUIDTimestampMixin, Base):
    __tablename__ = "submissions"

    round_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("rounds.id", ondelete="CASCADE"), nullable=False, index=True
    )
    contributor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    track_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tracks.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[SubmissionStatus] = mapped_column(
        default=SubmissionStatus.ACCEPTED, nullable=False, index=True
    )
    note: Mapped[str | None] = mapped_column(Text)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PolicyEvaluation(UUIDTimestampMixin, Base):
    __tablename__ = "policy_evaluations"

    round_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("rounds.id", ondelete="CASCADE"), nullable=False, index=True
    )
    submission_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("submissions.id", ondelete="SET NULL")
    )
    track_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tracks.id", ondelete="RESTRICT"), nullable=False
    )
    policy_kind: Mapped[str] = mapped_column(String(100), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    decision: Mapped[EvaluationDecision] = mapped_column(nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    result: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)


class ListeningEvidence(UUIDTimestampMixin, Base):
    __tablename__ = "listening_evidence"
    __table_args__ = (
        UniqueConstraint(
            "external_account_id", "track_id", "source", name="uq_listening_evidence_cache"
        ),
    )

    external_account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("external_accounts.id", ondelete="CASCADE"), nullable=False
    )
    track_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tracks.id", ondelete="CASCADE"), nullable=False
    )
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    playcount: Mapped[int | None] = mapped_column(Integer)
    last_played_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    match_confidence: Mapped[str] = mapped_column(String(32), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    refresh_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    response_status: Mapped[str] = mapped_column(String(32), nullable=False)


class Publication(UUIDTimestampMixin, Base):
    __tablename__ = "publications"
    __table_args__ = (UniqueConstraint("round_id", name="uq_publications_round"),)

    round_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("rounds.id", ondelete="CASCADE"), nullable=False
    )
    publisher_account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("external_accounts.id", ondelete="RESTRICT"), nullable=False
    )
    state: Mapped[PublicationState] = mapped_column(
        default=PublicationState.PENDING, nullable=False, index=True
    )
    spotify_playlist_id: Mapped[str | None] = mapped_column(String(128))
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    unpublished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PublicationItem(UUIDTimestampMixin, Base):
    __tablename__ = "publication_items"
    __table_args__ = (
        UniqueConstraint("publication_id", "position", name="uq_publication_items_position"),
    )

    publication_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("publications.id", ondelete="CASCADE"), nullable=False
    )
    submission_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("submissions.id", ondelete="SET NULL")
    )
    track_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tracks.id", ondelete="RESTRICT"), nullable=False
    )
    contributor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    note_snapshot: Mapped[str | None] = mapped_column(Text)


class AuditEvent(UUIDTimestampMixin, Base):
    __tablename__ = "audit_events"

    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
