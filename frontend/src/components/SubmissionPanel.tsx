import type { FormEvent } from "react";
import type { SpotifyTrackResult, SubmissionRecord } from "../types";

type SubmissionPanelProps = {
  submission: SubmissionRecord | null;
  isLoading: boolean;
  isLocked: boolean;
  notes: string;
  onNotesChange: (value: string) => void;
  onSearch: () => void;
  searchQuery: string;
  onSearchQueryChange: (value: string) => void;
  searchResults: SpotifyTrackResult[];
  searchLoading: boolean;
  resolveLoading: boolean;
  onSelectTrack: (track: SpotifyTrackResult) => void;
  message: string | null;
  error: string | null;
};

function SubmissionPanel({
  submission,
  isLoading,
  isLocked,
  notes,
  onNotesChange,
  onSearch,
  searchQuery,
  onSearchQueryChange,
  searchResults,
  searchLoading,
  resolveLoading,
  onSelectTrack,
  message,
  error,
}: SubmissionPanelProps) {
  const handleSubmitSearch = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!isLocked) onSearch();
  };

  const renderArtwork = (artworkUrl: string | null | undefined, label: string) => {
    const initial = label.trim().charAt(0).toUpperCase() || "♪";
    return artworkUrl ? (
      <img className="artwork" src={artworkUrl} alt={`${label} artwork`} loading="lazy" />
    ) : (
      <div className="artwork artwork--placeholder" aria-hidden="true">
        {initial}
      </div>
    );
  };

  const searchBusy = searchLoading || resolveLoading;
  const searchButtonLabel = resolveLoading ? "Loading track…" : searchLoading ? "Searching…" : "Search";

  return (
    <section className="card">
      <div className="card__header">
        <h2>Submit Your Track</h2>
      </div>
      <p className="muted">Choose one track per month. Update it anytime until the playlist is locked.</p>

      <div className="submission-status">
        {isLoading ? (
          <p className="muted">Loading your current submission…</p>
        ) : submission ? (
          <div className="submission-card">
            <div className="submission-card__artwork">
              {renderArtwork(submission.track.artwork_url ?? null, submission.track.name)}
            </div>
            <div>
              <span className="pill pill--spotify">Current pick</span>
              <h3>{submission.track.name}</h3>
              <p className="muted">{submission.track.artist}</p>
              {submission.track.album && <p className="muted small">Album: {submission.track.album}</p>}
              {submission.track.spotify_url && (
                <p>
                  <a className="link" href={submission.track.spotify_url} target="_blank" rel="noreferrer">
                    Open on Spotify
                  </a>
                </p>
              )}
            </div>
            <div className="submission-status__meta">
              <span className={submission.is_locked ? "pill pill--locked" : "pill"}>
                {submission.is_locked ? "Locked" : "Editable"}
              </span>
            </div>
          </div>
        ) : (
          <p className="muted">No submission for this month yet. Find a song below to add your pick.</p>
        )}
      </div>

      <label className="field">
        <span>Notes (optional)</span>
        <textarea
          rows={3}
          value={notes}
          onChange={(event) => onNotesChange(event.target.value)}
          placeholder="Share context or shout-outs for the playlist write-up."
          disabled={isLocked}
        />
      </label>

      <form className="submission-search" onSubmit={handleSubmitSearch}>
        <input type="search" placeholder="Search Spotify or paste a track link" value={searchQuery} onChange={(event) => onSearchQueryChange(event.target.value)} disabled={isLocked} />
        <button className="primary" type="submit" disabled={isLocked || searchBusy || !searchQuery.trim()}>
          {searchButtonLabel}
        </button>
      </form>
      {error && <p className="error">{error}</p>}
      {message && <p className="success">{message}</p>}

      {searchResults.length > 0 && !isLocked && (
        <div className="search-results">
          {searchResults.map((result) => (
            <button key={result.spotify_track_id} type="button" className="result" onClick={() => onSelectTrack(result)}>
              <div className="result__leading">
                {renderArtwork(result.artwork_url ?? null, result.name)}
              </div>
              <div className="result__details">
                <h4>{result.name}</h4>
                <p className="muted">{result.artist}</p>
                {result.album && <p className="muted small">{result.album}</p>}
              </div>
              <span className="pill pill--cta">Choose</span>
            </button>
          ))}
        </div>
      )}

      {isLocked && <p className="muted small">Submissions are locked once the playlist is finalized. Ask an admin if you need changes.</p>}
    </section>
  );
}

export default SubmissionPanel;
