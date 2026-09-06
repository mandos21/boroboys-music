import { useDeferredValue, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router";

import { api, post } from "../../api/client";
import type { components } from "../../api/schema";

type Round = {
  id: string;
  title: string;
  status: string;
  opensAt: string;
  closesAt: string;
  publishAt: string;
  submissionLimit: number;
};

type Track = {
  spotifyTrackId: string;
  name: string;
  artist: string;
  album: string | null;
  spotifyUri: string | null;
  artworkUrl: string | null;
  providerMetadata: Record<string, unknown>;
};

type PolicyResult = {
  kind: string;
  decision: "accept" | "warn" | "reject";
  message: string;
};

type Evaluation = {
  trackId: string;
  canSubmit: boolean;
  limitRemaining: number;
  requiresWarningConfirmation: boolean;
  policyResults: PolicyResult[];
};

type Evidence = {
  evidence: Array<{
    accountId: string;
    displayName: string | null;
    playcount: number | null;
    fetchedAt: string;
    refreshAfter: string | null;
    status: string;
  }>;
};

type SubmissionResult = {
  accepted: boolean;
  id?: string;
  requiresWarningConfirmation?: boolean;
  policyResults: PolicyResult[];
};

type TrackInput = components["schemas"]["TrackInput"];
type TrackEvaluationRequest = components["schemas"]["TrackEvaluationRequest"];
type SubmissionCreate = components["schemas"]["SubmissionCreate"];

function asTrackInput(track: Track): TrackInput {
  return {
    spotify_track_id: track.spotifyTrackId,
    name: track.name,
    artist: track.artist,
    album: track.album,
    spotify_uri: track.spotifyUri,
    artwork_url: track.artworkUrl,
    provider_metadata: track.providerMetadata,
  };
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

function SearchResult({ track, onSelect }: { track: Track; onSelect: (track: Track) => void }) {
  return (
    <button className="track-result" type="button" onClick={() => onSelect(track)}>
      {track.artworkUrl ? <img src={track.artworkUrl} alt="" /> : <span className="cover-placeholder" aria-hidden="true">♫</span>}
      <span><strong>{track.name}</strong><small>{track.artist}{track.album ? ` · ${track.album}` : ""}</small></span>
      <span aria-hidden="true">+</span>
    </button>
  );
}

export function SubmissionPage() {
  const { roundId } = useParams();
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<Track | null>(null);
  const [note, setNote] = useState("");
  const [confirmWarnings, setConfirmWarnings] = useState(false);
  const deferredQuery = useDeferredValue(query.trim());
  const round = useQuery({ queryKey: ["round", roundId], queryFn: () => api<Round>(`/rounds/${roundId}`), enabled: Boolean(roundId), retry: false });
  const tracks = useQuery({
    queryKey: ["track-search", roundId, deferredQuery],
    queryFn: () => api<Track[]>(`/rounds/${roundId}/track-search?query=${encodeURIComponent(deferredQuery)}`),
    enabled: Boolean(roundId) && deferredQuery.length >= 2,
  });
  const evaluation = useMutation({
    mutationFn: (track: Track) => {
      const request: TrackEvaluationRequest = { track: asTrackInput(track) };
      return post<Evaluation>(`/rounds/${roundId}/evaluate-track`, request);
    },
  });
  const evidence = useQuery({
    queryKey: ["evidence", roundId, evaluation.data?.trackId],
    queryFn: () => api<Evidence>(`/rounds/${roundId}/tracks/${evaluation.data?.trackId}/evidence`),
    enabled: Boolean(roundId && evaluation.data?.trackId),
  });
  const submission = useMutation({
    mutationFn: () => {
      if (!selected) throw new Error("Select a track before submitting.");
      const request: SubmissionCreate = {
        track: asTrackInput(selected),
        note: note || null,
        confirm_warnings: confirmWarnings,
      };
      return post<SubmissionResult>(`/rounds/${roundId}/submissions`, request);
    },
    onSuccess: (result) => {
      if (result.accepted) navigate(`/rounds/${roundId}`);
    },
  });

  function chooseTrack(track: Track) {
    setSelected(track);
    setConfirmWarnings(false);
    evaluation.reset();
    submission.reset();
    evaluation.mutate(track);
  }

  if (round.isLoading) return <main className="shell"><p>Loading submission form…</p></main>;
  if (round.isError || !round.data) return <main className="shell"><section className="panel"><h1>Round unavailable</h1><Link to="/">Return to your rounds</Link></section></main>;
  if (round.data.status !== "open") return <main className="shell"><section className="panel"><h1>This round is not accepting submissions</h1><p>It closes {formatDate(round.data.closesAt)}.</p><Link to={`/rounds/${roundId}`}>View round</Link></section></main>;

  const policyResults = evaluation.data?.policyResults ?? submission.data?.policyResults ?? [];
  const canSubmit = Boolean(selected && evaluation.data?.canSubmit && !submission.isPending);
  return (
    <main className="shell submission-shell">
      <Link className="back" to={`/rounds/${roundId}`}>← {round.data.title}</Link>
      <header className="submission-heading"><p className="eyebrow">Your submission</p><h1>Choose a track.</h1><p>You have room for {evaluation.data?.limitRemaining ?? round.data.submissionLimit} submissions in this round.</p></header>
      <div className="submission-layout">
        <section className="panel search-panel">
          <label htmlFor="track-search">Search Spotify</label>
          <input id="track-search" autoComplete="off" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Song, artist, or album" />
          {query.trim().length > 0 && query.trim().length < 2 && <p className="field-hint">Enter at least two characters.</p>}
          {tracks.isFetching && <p className="field-hint">Searching Spotify…</p>}
          {tracks.isError && <p className="error-message" role="alert">Spotify search is unavailable. Confirm your Spotify account is linked and try again.</p>}
          <div className="track-results">
            {tracks.data?.map((track) => <SearchResult key={track.spotifyTrackId} track={track} onSelect={chooseTrack} />)}
            {tracks.data?.length === 0 && deferredQuery.length >= 2 && !tracks.isFetching && <p className="field-hint">No matching tracks found.</p>}
          </div>
        </section>
        <section className="panel review-panel" aria-live="polite">
          <h2>Review</h2>
          {!selected && <p>Select a Spotify track to check it against this round&apos;s rules.</p>}
          {selected && <div className="selected-track">{selected.artworkUrl ? <img src={selected.artworkUrl} alt="" /> : null}<div><h3>{selected.name}</h3><p>{selected.artist}{selected.album ? ` · ${selected.album}` : ""}</p></div></div>}
          {evaluation.isPending && <p>Checking rules and listening evidence…</p>}
          {evaluation.isError && <p className="error-message" role="alert">The track could not be evaluated. Try selecting it again.</p>}
          {policyResults.length > 0 && <div className="policy-results"><h3>Round checks</h3>{policyResults.map((result) => <p className={`policy ${result.decision}`} key={`${result.kind}-${result.message}`}>{result.message}</p>)}</div>}
          {evidence.isFetching && <p className="field-hint">Loading cached listening evidence…</p>}
          {evidence.data && <div className="evidence"><h3>Group listening evidence</h3>{evidence.data.evidence.length === 0 ? <p className="field-hint">No shared Last.fm evidence is cached yet. It will refresh in the background.</p> : evidence.data.evidence.map((item) => <p key={item.accountId}><strong>{item.displayName ?? "A contributor"}</strong>: at least {item.playcount ?? 0} listens <small>observed {formatDate(item.fetchedAt)}</small></p>)}</div>}
          {evaluation.data?.requiresWarningConfirmation && <label className="confirmation"><input type="checkbox" checked={confirmWarnings} onChange={(event) => setConfirmWarnings(event.target.checked)} /> I understand the warning and want to submit this track.</label>}
          <label className="note-label" htmlFor="submission-note">Optional note</label>
          <textarea id="submission-note" value={note} maxLength={4000} onChange={(event) => setNote(event.target.value)} placeholder="Why this track?" />
          {submission.isError && <p className="error-message" role="alert">{submission.error.message}</p>}
          {submission.data && !submission.data.accepted && <p className="error-message" role="alert">{submission.data.requiresWarningConfirmation ? "Confirm the warning before submitting." : "This track cannot be submitted under the current rules."}</p>}
          <button className="button" type="button" disabled={!canSubmit || (evaluation.data?.requiresWarningConfirmation && !confirmWarnings)} onClick={() => submission.mutate()}>{submission.isPending ? "Submitting…" : "Submit track"}</button>
        </section>
      </div>
    </main>
  );
}
