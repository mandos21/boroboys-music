import { useState, type FormEvent } from "react";
import type { ImportAssignments, PlaylistImportPayload, UserSummary } from "../types";

type AdminPlaylistImportProps = {
  users: UserSummary[];
  onImport: (ref: string, month: string) => Promise<void>;
  busy: boolean;
  payload: PlaylistImportPayload | null;
  onSave: () => Promise<void>;
  saving: boolean;
  assignments: ImportAssignments;
  onAssignmentChange: (position: number, key: "user_id" | "notes", value: string) => void;
  lockSubmissions: boolean;
  onToggleLock: () => void;
  statusMessage: string | null;
};

function AdminPlaylistImport({
  users,
  onImport,
  busy,
  payload,
  onSave,
  saving,
  assignments,
  onAssignmentChange,
  lockSubmissions,
  onToggleLock,
  statusMessage,
}: AdminPlaylistImportProps) {
  const [playlistRef, setPlaylistRef] = useState("");
  const [playlistMonth, setPlaylistMonth] = useState(() => {
    const now = new Date();
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
  });
  const [error, setError] = useState<string | null>(null);

  const handleImport = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    try {
      await onImport(playlistRef.trim(), playlistMonth);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unable to load playlist";
      setError(message);
    }
  };

  return (
    <section className="card">
      <div className="card__header">
        <h2>Backfill Spotify Playlist</h2>
      </div>
      <p className="muted">Import an existing Spotify playlist and optionally assign each track to a crew member.</p>
      <form className="import-form" onSubmit={handleImport}>
        <div className="field">
          <label>Spotify playlist link or ID</label>
          <input value={playlistRef} onChange={(event) => setPlaylistRef(event.target.value)} placeholder="https://open.spotify.com/playlist/..." required />
        </div>
        <div className="field">
          <label>Playlist month</label>
          <input type="month" value={playlistMonth} onChange={(event) => setPlaylistMonth(event.target.value)} required />
        </div>
        <button className="primary" type="submit" disabled={busy}>
          {busy ? "Loading…" : "Fetch playlist"}
        </button>
      </form>
      {error && <p className="error">{error}</p>}
      {statusMessage && <p className="success">{statusMessage}</p>}

      {payload && (
        <div className="import-preview">
          <header>
            <h3>{payload.name}</h3>
            <p className="muted">{payload.tracks.length} tracks · {payload.playlist_month}</p>
            {payload.description && <p className="muted small">{payload.description}</p>}
          </header>
          <div className="import-table">
            <div className="import-table__row import-table__row--head">
              <span>#</span>
              <span>Track</span>
              <span>Assign to</span>
              <span>Notes</span>
            </div>
            {payload.tracks.map((track) => (
              <div className="import-table__row" key={`${track.spotify_track_id}-${track.position}`}>
                <span>{track.position}</span>
                <div>
                  <p className="strong">{track.name}</p>
                  <p className="muted small">{track.artists || track.artist}</p>
                </div>
                <select value={assignments[track.position]?.user_id ?? ""} onChange={(event) => onAssignmentChange(track.position, "user_id", event.target.value)}>
                  <option value="">—</option>
                  {users.map((member) => (
                    <option key={member.id} value={String(member.id)}>
                      {member.display_name?.trim() || member.username}
                    </option>
                  ))}
                </select>
                <input value={assignments[track.position]?.notes ?? ""} onChange={(event) => onAssignmentChange(track.position, "notes", event.target.value)} placeholder="Notes" />
              </div>
            ))}
          </div>
          <div className="import-actions">
            <label className="toggle">
              <input type="checkbox" checked={lockSubmissions} onChange={onToggleLock} />
              <span>Lock submissions for assigned tracks</span>
            </label>
            <button className="primary" onClick={onSave} disabled={saving}>
              {saving ? "Saving…" : "Save playlist"}
            </button>
          </div>
        </div>
      )}
    </section>
  );
}

export default AdminPlaylistImport;
