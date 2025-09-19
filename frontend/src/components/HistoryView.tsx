import type { PlaylistRecord } from "../types";

type HistoryViewProps = {
  playlists: PlaylistRecord[];
  loading: boolean;
  onSelect: (playlistId: number) => void;
  selected: PlaylistRecord | null;
  detailLoading: boolean;
  detailError: string | null;
};

const formatPlaylistLabel = (playlist: PlaylistRecord) =>
  new Date(playlist.month).toLocaleString(undefined, { month: "long", year: "numeric" });

const formatDuration = (durationMs?: number | null) => {
  if (!durationMs) return "—";
  const totalSeconds = Math.floor(durationMs / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
};

function HistoryView({ playlists, loading, onSelect, selected, detailLoading, detailError }: HistoryViewProps) {
  const renderAvatar = (avatarUrl: string | null | undefined, name: string | null | undefined) => {
    const initial = (name || "?").trim().charAt(0).toUpperCase() || "?";
    return avatarUrl ? (
      <img className="avatar" src={avatarUrl} alt={`${name ?? "Listener"} profile`} loading="lazy" />
    ) : (
      <div className="avatar avatar--fallback" aria-hidden="true">
        {initial}
      </div>
    );
  };

  return (
    <section className="history-shell">
      <aside className="history-list">
        <h2>Playlist History</h2>
        {loading ? (
          <p className="muted">Loading playlists…</p>
        ) : playlists.length === 0 ? (
          <p className="muted">No playlists published yet.</p>
        ) : (
          playlists.map((playlist) => (
            <button
              key={playlist.id}
              type="button"
              className={`history-list__item${selected?.id === playlist.id ? " history-list__item--active" : ""}`}
              onClick={() => onSelect(playlist.id)}
            >
              <span>{formatPlaylistLabel(playlist)}</span>
              <span className="muted small">{playlist.tracks.length} tracks</span>
            </button>
          ))
        )}
      </aside>
      <section className="card history-detail">
        {detailLoading ? (
          <p className="muted">Loading playlist details…</p>
        ) : detailError ? (
          <p className="error">{detailError}</p>
        ) : selected ? (
          <div className="history-detail__content">
            <header>
              <h3>{formatPlaylistLabel(selected)}</h3>
              {selected.spotify_playlist_id && (
                <a className="link" href={`https://open.spotify.com/playlist/${selected.spotify_playlist_id}`} target="_blank" rel="noreferrer">
                  Open on Spotify
                </a>
              )}
              {selected.description && <p className="muted small">{selected.description}</p>}
            </header>
            <ul className="tracklist">
              {selected.tracks.map((entry) => (
                <li className="tracklist__item" key={`${selected.id}-${entry.position}`}>
                  <div className="tracklist__left">
                    <span className="tracklist__title">{entry.position}. {entry.track.name}</span>
                    <span className="tracklist__meta">{entry.track.artist}{entry.track.album ? ` · ${entry.track.album}` : ""}</span>
                    {entry.submitter_name && (
                      <div className="tracklist__byline">
                        {renderAvatar(entry.submitter_avatar_url ?? null, entry.submitter_name)}
                        <span className="tracklist__submitter">Submitted by {entry.submitter_name}</span>
                      </div>
                    )}
                    {entry.submitter_notes && <span className="muted small">{entry.submitter_notes}</span>}
                  </div>
                  <div className="tracklist__right">
                    <span className="tracklist__duration">{formatDuration(entry.track.duration_ms)}</span>
                    {entry.track.spotify_url && (
                      <a className="pill pill--cta" href={entry.track.spotify_url} target="_blank" rel="noreferrer">
                        Open
                      </a>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          </div>
        ) : (
          <p className="muted">Select a playlist to see track details.</p>
        )}
      </section>
    </section>
  );
}

export default HistoryView;
