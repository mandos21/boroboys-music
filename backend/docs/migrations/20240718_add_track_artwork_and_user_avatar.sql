ALTER TABLE tracks
    ADD COLUMN artwork_url VARCHAR(500);

ALTER TABLE users
    ADD COLUMN spotify_avatar_url VARCHAR(500);
