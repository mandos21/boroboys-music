import type { FormEvent } from "react";
import type { SpotifyTrackResult, SubmissionRecord } from "../types";

type SubmissionPanelProps = {
  submissions: SubmissionRecord[];
  isLoading: boolean;
  isLocked: boolean;
  limit: number | null;
  used: number;
  remaining: number | null;
  notes: string;
  onNotesChange: (value: string) => void;
  onSearch: () => void;
  searchQuery: string;
  onSearchQueryChange: (value: string) => void;
  searchResults: SpotifyTrackResult[];
  searchLoading: boolean;
  resolveLoading: boolean;
  onSelectTrack: (track: SpotifyTrackResult) => void;
  onDeleteSubmission: (submissionId: number) => void;
  message: string | null;
  error: string | null;
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

const formatLimitLabel = (limit: number | null, used: number) => {
  if (limit == null) return `${used} submission${used === 1 ? "" : "s"}`;
  return `${used} / ${limit} submissions`;
};

function SubmissionPanel({
  submissions,
  isLoading,
  isLocked,
  limit,
  used,
  remaining,
  notes,
  onNotesChange,
  onSearch,
  searchQuery,
  onSearchQueryChange,
  searchResults,
  searchLoading,
  resolveLoading,
  onSelectTrack,
  onDeleteSubmission,
  message,
  error,
}: SubmissionPanelProps) {
  const canAdd = !isLocked && (remaining == null || remaining > 0);
  const handleSubmitSearch = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!canAdd) return;
    onSearch();
  };

  const searchBusy = searchLoading || resolveLoading;
  const searchButtonLabel = resolveLoading ? "Loading track…" : searchLoading ? "Searching…" : "Search";
  const limitLabel = formatLimitLabel(limit, used);

  return (
    <section className="card">
      <div className="card__header">
        <h2>Submit Your Tracks</h2>
        <span className="muted small">{limitLabel}</span>
      </div>
      <p className="muted">
        Add tracks for this month up to your personal limit. You can remove a track before the playlist is released.
      </p>

      <div className="submission-status">
        {isLoading ? (
          <p className="muted">Loading your submissions…</p>
        ) : submissions.length === 0 ? (
          <p className="muted">No submissions yet. Use the search below to add your first track.</p>
        ) : (
          <ul className="submission-list">
            {submissions.map((submission) => (
              <li key={submission.id} className="submission-card">
                <div className="submission-card__artwork">
                  {renderArtwork(submission.track.artwork_url ?? null, submission.track.name)}
                </div>
                <div className="submission-card__content">
                  <span className="pill pill--spotify">Current pick</span>
                  <h3>{submission.track.name}</h3>
                  <p className="muted">{submission.track.artist}</p>
                  {submission.track.album && <p className="muted small">Album: {submission.track.album}</p>}
                  {submission.notes && <p className="muted small">Notes: {submission.notes}</p>}
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
                  {!submission.is_locked && !isLocked && (
                    <button className="secondary small" type="button" onClick={() => onDeleteSubmission(submission.id)}>
                      Remove
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      <label className="field">
        <span>Notes (optional)</span>
        <textarea
          rows={3}
          value={notes}
          onChange={(event) => onNotesChange(event.target.value)}
          placeholder="Share context or shout-outs for the playlist write-up."
          disabled={!canAdd}
        />
      </label>

      <form className="submission-search" onSubmit={handleSubmitSearch}>
        <input
          type="search"
          placeholder="Search Spotify or paste a track link"
          value={searchQuery}
          onChange={(event) => onSearchQueryChange(event.target.value)}
          disabled={!canAdd}
        />
        <button className="primary" type="submit" disabled={!canAdd || searchBusy || !searchQuery.trim()}>
          {searchButtonLabel}
        </button>
      </form>
      {remaining === 0 && !isLocked && <p className="muted small">You have reached your submission limit for this month.</p>}
      {error && <p className="error">{error}</p>}
      {message && <p className="success">{message}</p>}

      {searchResults.length > 0 && canAdd && (
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
