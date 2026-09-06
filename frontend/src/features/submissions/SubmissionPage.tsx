import { useDeferredValue, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Link, useNavigate, useParams, useSearchParams } from "react-router";

import { api, patch, post } from "../../api/client";
import { formatDate } from "../../lib/format";
import { SubmissionReviewPanel } from "./SubmissionReviewPanel";
import { TrackSearchPanel } from "./TrackSearchPanel";
import {
  asTrackInput,
  type Evidence,
  type Evaluation,
  type Round,
  type SubmissionCreate,
  type SubmissionResult,
  type Track,
  type TrackEvaluationRequest,
} from "./types";

export function SubmissionPage() {
  const { roundId } = useParams();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const replaceId = searchParams.get("replace");
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
      if (replaceId) {
        // Omitting note preserves the existing note during a track-only replacement.
        return patch<SubmissionResult>(`/rounds/submissions/${replaceId}`, {
          track: request.track,
          confirm_warnings: request.confirm_warnings,
        });
      }
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
      <header className="submission-heading"><p className="eyebrow">Your submission</p><h1>{replaceId ? "Replace your track." : "Choose a track."}</h1><p>{replaceId ? "The new track must pass the same round checks before it replaces your existing submission." : `You have room for ${evaluation.data?.limitRemaining ?? round.data.submissionLimit} submissions in this round.`}</p></header>
      <div className="submission-layout">
        <TrackSearchPanel query={query} deferredQuery={deferredQuery} isSearching={tracks.isFetching} hasError={tracks.isError} tracks={tracks.data} onQueryChange={setQuery} onSelect={chooseTrack} />
        <SubmissionReviewPanel
          selected={selected}
          isEvaluating={evaluation.isPending}
          evaluationFailed={evaluation.isError}
          policyResults={policyResults}
          isLoadingEvidence={evidence.isFetching}
          evidence={evidence.data}
          requiresWarningConfirmation={Boolean(evaluation.data?.requiresWarningConfirmation)}
          confirmWarnings={confirmWarnings}
          onConfirmWarningsChange={setConfirmWarnings}
          isReplacing={Boolean(replaceId)}
          note={note}
          onNoteChange={setNote}
          submissionError={submission.isError ? submission.error : null}
          submissionResult={submission.data}
          isSubmitting={submission.isPending}
          canSubmit={canSubmit}
          onSubmit={() => submission.mutate()}
        />
      </div>
    </main>
  );
}
