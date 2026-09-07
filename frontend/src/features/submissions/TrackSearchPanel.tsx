import { Link } from "react-router";

import type { Track } from "./types";

type TrackSearchPanelProps = {
  query: string;
  deferredQuery: string;
  isSearching: boolean;
  hasError: boolean;
  tracks: Track[] | undefined;
  onQueryChange: (value: string) => void;
  onSelect: (track: Track) => void;
  suggestions?: Array<{ name: string; artist: string; artworkUrl: string | null }>;
  onSuggestion: (suggestion: { name: string; artist: string; artworkUrl: string | null }) => void;
};

function SearchResult({ track, onSelect }: { track: Track; onSelect: (track: Track) => void }) {
  return (
    <button className="track-result" type="button" onClick={() => onSelect(track)}>
      {track.artworkUrl ? <img src={track.artworkUrl} alt="" /> : <span className="cover-placeholder" aria-hidden="true">♫</span>}
      <span>
        <strong>{track.name}</strong>
        <small>{track.artist}{track.album ? ` · ${track.album}` : ""}</small>
      </span>
      <span aria-hidden="true">+</span>
    </button>
  );
}

export function TrackSearchPanel({
  query,
  deferredQuery,
  isSearching,
  hasError,
  tracks,
  onQueryChange,
  onSelect,
  suggestions,
  onSuggestion,
}: TrackSearchPanelProps) {
  return (
    <section className="panel search-panel" aria-label="Find a Spotify track">
      <label htmlFor="track-search">Search Spotify</label>
      <input
        id="track-search"
        autoComplete="off"
        value={query}
        onChange={(event) => onQueryChange(event.target.value)}
        placeholder="Song, artist, or album"
      />
      {query.trim().length > 0 && query.trim().length < 2 && <p className="field-hint">Enter at least two characters.</p>}
      {isSearching && <p className="field-hint" role="status">Searching Spotify…</p>}
      {hasError && <p className="error-message" role="alert">Spotify search is unavailable. <Link to="/settings/connections">Check your Spotify connection</Link> and try again.</p>}
      {suggestions && suggestions.length > 0 && !query.trim() && (
        <div className="listening-suggestions">
          <p className="eyebrow">Your month on Last.fm</p>
          <p className="field-hint">Start with something you have been returning to lately.</p>
          <div>{suggestions.map((suggestion) => <button key={`${suggestion.artist}-${suggestion.name}`} type="button" onClick={() => onSuggestion(suggestion)}>{suggestion.artworkUrl ? <img src={suggestion.artworkUrl} alt="" /> : <span className="suggestion-artwork-placeholder" aria-hidden="true">♫</span>}<span><strong>{suggestion.name}</strong><small>{suggestion.artist}</small></span></button>)}</div>
        </div>
      )}
      <div className="track-results">
        {tracks?.map((track) => <SearchResult key={track.spotifyTrackId} track={track} onSelect={onSelect} />)}
        {tracks?.length === 0 && deferredQuery.length >= 2 && !isSearching && <p className="field-hint">No matching tracks found.</p>}
      </div>
    </section>
  );
}
