"""add canonical track artists, genres, and profile history index

Revision ID: a1e6d7c9b2f4
Revises: d84e1f2a6b3c
Create Date: 2026-09-08 10:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1e6d7c9b2f4"
down_revision: str | None = "d84e1f2a6b3c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("tracks", sa.Column("spotify_album_id", sa.String(length=64)))
    op.create_table(
        "track_artists",
        sa.Column("track_id", sa.UUID(), nullable=False),
        sa.Column("spotify_artist_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=500), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["track_id"], ["tracks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("track_id", "spotify_artist_id"),
    )
    op.create_index("ix_track_artists_spotify_artist_id", "track_artists", ["spotify_artist_id"])
    op.create_table(
        "track_genres",
        sa.Column("track_id", sa.UUID(), nullable=False),
        sa.Column("genre_key", sa.String(length=200), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.ForeignKeyConstraint(["track_id"], ["tracks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("track_id", "genre_key"),
    )
    op.create_index("ix_track_genres_genre_key", "track_genres", ["genre_key"])
    op.create_index(
        "ix_submissions_profile_history",
        "submissions",
        ["contributor_id", "status", "submitted_at"],
    )

    # Old imports have only display strings. Preserve their existing behavior as
    # one legacy credit until a later trusted Spotify refresh replaces it.
    op.execute(
        """
        INSERT INTO track_artists (track_id, spotify_artist_id, name, position)
        SELECT id, 'legacy:' || id::text, artist, 0
        FROM tracks
        """
    )
    # Preserve historic best-effort genre tags in the durable, additive store.
    op.execute(
        """
        INSERT INTO track_genres (track_id, genre_key, name)
        SELECT tracks.id, lower(trim(genre.value)), trim(genre.value)
        FROM tracks
        CROSS JOIN LATERAL jsonb_array_elements_text(
            COALESCE(tracks.provider_metadata->'genres', '[]'::jsonb)
        ) AS genre(value)
        WHERE trim(genre.value) <> ''
        ON CONFLICT (track_id, genre_key) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index("ix_submissions_profile_history", table_name="submissions")
    op.drop_index("ix_track_genres_genre_key", table_name="track_genres")
    op.drop_table("track_genres")
    op.drop_index("ix_track_artists_spotify_artist_id", table_name="track_artists")
    op.drop_table("track_artists")
    op.drop_column("tracks", "spotify_album_id")
