ALTER TABLE playlist_tracks
    ADD COLUMN submitter_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    ADD COLUMN submitter_notes VARCHAR(500);

-- Optional: backfill submitter_id from existing submissions
UPDATE playlist_tracks pt
SET submitter_id = s.user_id,
    submitter_notes = COALESCE(pt.submitter_notes, s.notes)
FROM submissions s
WHERE s.track_id = pt.track_id
  AND s.submission_month = (SELECT month FROM playlists WHERE id = pt.playlist_id);
