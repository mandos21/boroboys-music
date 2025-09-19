import type { FormEvent } from "react";
import type { SpotifyTrackResult } from "../types";

type LookupPanelProps = {
  query: string;
  onQueryChange: (value: string) => void;
  onSearch: () => void;
  loading: boolean;
  results: SpotifyTrackResult[];
  error: string | null;
};

function LookupPanel({ query, onQueryChange, onSearch, loading, results, error }: LookupPanelProps) {
  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    onSearch();
  };

  return (
    <section className="card">
      <div className="card__header">
        <h2>Song Lookup</h2>
      </div>
      <form className="lookup-form" onSubmit={handleSubmit}>
        <div className="field">
          <label>Search term</label>
          <input type="search" placeholder="Artist, track, or album" value={query} onChange={(event) => onQueryChange(event.target.value)} />
        </div>
        <button className="primary" type="submit" disabled={!query.trim() || loading}>
          {loading ? "Searching…" : "Search"}
        </button>
      </form>
      {error && <p className="error">{error}</p>}
      {loading ? (
        <p className="muted">Searching Spotify…</p>
      ) : results.length > 0 ? (
        <div className="search-results">
          {results.map((result) => (
            <div key={result.spotify_track_id} className="result result--static">
              <div>
                <h4>{result.name}</h4>
                <p className="muted">
                  {result.artist}
                  {result.album ? ` · ${result.album}` : ""}
                </p>
              </div>
              {result.spotify_url && (
                <a className="pill pill--cta" href={result.spotify_url} target="_blank" rel="noreferrer">
                  Open
                </a>
              )}
            </div>
          ))}
        </div>
      ) : (
        <p className="muted">No results yet. Try searching for a track.</p>
      )}
    </section>
  );
}

export default LookupPanel;
