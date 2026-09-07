import { useDeferredValue, useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Link, useNavigate, useParams, useSearchParams } from "react-router";

import { api, patch, post, put } from "../../api/client";
import { StatePanel } from "../../components/ui/StatePanel";
import { useToast } from "../../components/ui/ToastProvider";
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
  type SubmissionDraft,
  type Track,
  type TrackEvaluationRequest,
  trackFromInput,
} from "./types";

export function SubmissionPage() {
  const { roundId } = useParams();
  const navigate = useNavigate();
  const { showToast } = useToast();
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
  const draft = useQuery({ queryKey: ["submission-draft", roundId], queryFn: () => api<SubmissionDraft>(`/rounds/${roundId}/draft`), enabled: Boolean(roundId && !replaceId), retry: false });
  const suggestions = useQuery({ queryKey: ["listening-suggestions", roundId], queryFn: () => api<Array<{ name: string; artist: string }>>(`/rounds/${roundId}/listening-suggestions`), enabled: Boolean(roundId && !replaceId), retry: false });
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
      if (result.accepted) {
        showToast({ title: replaceId ? "Track replaced" : "Track submitted", description: "Your choice is now part of this round." });
        navigate(`/rounds/${roundId}`);
      }
    },
    onError: () => showToast({ title: "Couldn’t save submission", description: "Your track was not submitted. Please try again.", tone: "error" }),
  });

  function chooseTrack(track: Track) {
    setSelected(track);
    setConfirmWarnings(false);
    evaluation.reset();
    submission.reset();
    evaluation.mutate(track);
  }

  useEffect(() => {
    if (!selected && draft.data?.track) {
      chooseTrack(trackFromInput(draft.data.track));
      setNote(draft.data.note ?? "");
    }
  }, [draft.data]);

  useEffect(() => {
    if (!roundId || replaceId || !draft.isSuccess) return;
    const timer = window.setTimeout(() => {
      void put(`/rounds/${roundId}/draft`, { track: selected ? asTrackInput(selected) : null, note: note || null });
    }, 700);
    return () => window.clearTimeout(timer);
  }, [draft.isSuccess, note, replaceId, roundId, selected]);

  if (round.isLoading) return <main className="shell narrow-page-shell"><StatePanel kind="loading" title="Preparing your submission">Loading the round’s rules and timing.</StatePanel></main>;
  if (round.isError || !round.data) return <main className="shell narrow-page-shell"><StatePanel kind="error" title="Round unavailable"><Link to="/">Return to your rounds</Link></StatePanel></main>;
  if (round.data.status !== "open") return <main className="shell narrow-page-shell"><StatePanel title="This round is not accepting submissions">It closes {formatDate(round.data.closesAt)}. <Link to={`/rounds/${roundId}`}>View round</Link></StatePanel></main>;

  const policyResults = evaluation.data?.policyResults ?? submission.data?.policyResults ?? [];
  const canSubmit = Boolean(selected && evaluation.data?.canSubmit && !submission.isPending);
  return (
    <main className="shell submission-shell">
      <Link className="back" to={`/rounds/${roundId}`}>← {round.data.title}</Link>
      <header className="submission-heading"><p className="eyebrow">Your submission</p><h1>{replaceId ? "Replace your track." : "Choose a track."}</h1><p>{replaceId ? "The new track must pass the same round checks before it replaces your existing submission." : `You have room for ${evaluation.data?.limitRemaining ?? round.data.submissionLimit} submissions in this round.`}</p>{round.data.prompt && <p className="round-prompt">Prompt: {round.data.prompt}</p>}</header>
      <div className="submission-layout">
        <TrackSearchPanel query={query} deferredQuery={deferredQuery} isSearching={tracks.isFetching} hasError={tracks.isError} tracks={tracks.data} onQueryChange={setQuery} onSelect={chooseTrack} suggestions={suggestions.data} onSuggestion={(suggestion) => setQuery(`${suggestion.artist} ${suggestion.name}`)} />
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
