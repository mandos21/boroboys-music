import { useCallback, useDeferredValue, useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm, useWatch } from "react-hook-form";
import { Link, useNavigate, useParams, useSearchParams } from "react-router";

import { api, patch, post, put } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import { StatePanel } from "../../components/ui/StatePanel";
import { MobileActionBar } from "../../components/ui/MobileActionBar";
import { PageSkeleton } from "../../components/ui/PageSkeleton";
import { useToast } from "../../components/ui/ToastProvider";
import { Button } from "../../components/ui/button";
import { formatDate } from "../../lib/format";
import { SubmissionReviewPanel } from "./SubmissionReviewPanel";
import { TrackSearchPanel } from "./TrackSearchPanel";
import {
  asTrackInput,
  type Evidence,
  type Evaluation,
  type Round,
  type Submission,
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
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const [searchParams] = useSearchParams();
  const replaceId = searchParams.get("replace");
  const [query, setQuery] = useState("");
  const [confirmWarnings, setConfirmWarnings] = useState(false);
  const submittedRef = useRef(false);
  const draftPayloadRef = useRef<{ track: Track | null; note: string }>({ track: null, note: "" });
  const form = useForm<{ selected: Track | null; note: string }>({
    defaultValues: { selected: null, note: "" },
  });
  const selected = useWatch({ control: form.control, name: "selected" });
  const note = useWatch({ control: form.control, name: "note" });
  const deferredQuery = useDeferredValue(query.trim());
  const round = useQuery({
    queryKey: queryKeys.round(roundId),
    queryFn: () => api<Round>(`/rounds/${roundId}`),
    enabled: Boolean(roundId),
    retry: false,
  });
  const tracks = useQuery({
    queryKey: queryKeys.trackSearch(roundId, deferredQuery),
    queryFn: () =>
      api<Track[]>(`/rounds/${roundId}/track-search?query=${encodeURIComponent(deferredQuery)}`),
    enabled: Boolean(roundId) && deferredQuery.length >= 2,
  });
  const evaluation = useMutation({
    mutationFn: (track: Track) => {
      const request: TrackEvaluationRequest = {
        track: asTrackInput(track),
        replacing_submission_id: replaceId ?? undefined,
      };
      return post<Evaluation>(`/rounds/${roundId}/evaluate-track`, request);
    },
  });
  const evidence = useQuery({
    queryKey: queryKeys.evidence(roundId, evaluation.data?.trackId),
    queryFn: () => api<Evidence>(`/rounds/${roundId}/tracks/${evaluation.data?.trackId}/evidence`),
    enabled: Boolean(roundId && evaluation.data?.trackId),
  });
  const draft = useQuery({
    queryKey: queryKeys.submissionDraft(roundId),
    queryFn: () => api<SubmissionDraft>(`/rounds/${roundId}/draft`),
    enabled: Boolean(roundId && !replaceId),
    retry: false,
  });
  // The round detail counts contributors, not this person's own entries, so
  // the remaining allowance comes from the submissions the page already shares
  // with the round view rather than from the round's total limit.
  const submissions = useQuery({
    queryKey: queryKeys.roundSubmissions(roundId),
    queryFn: () => api<Submission[]>(`/rounds/${roundId}/submissions`),
    enabled: Boolean(roundId),
    retry: false,
  });
  const suggestions = useQuery({
    queryKey: queryKeys.listeningSuggestions(roundId),
    queryFn: () =>
      api<Array<{ name: string; artist: string; artworkUrl: string | null }>>(
        `/rounds/${roundId}/listening-suggestions`,
      ),
    enabled: Boolean(roundId && !replaceId),
    retry: false,
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
      if (result.accepted) {
        submittedRef.current = true;
        void queryClient.invalidateQueries({ queryKey: queryKeys.round(roundId) });
        void queryClient.invalidateQueries({ queryKey: queryKeys.roundSubmissions(roundId) });
        void queryClient.invalidateQueries({ queryKey: queryKeys.series() });
        showToast({
          title: replaceId ? "Track replaced" : "Track submitted",
          description: "Your choice is now part of this round.",
        });
        navigate(`/rounds/${roundId}`);
      }
    },
    onError: () =>
      showToast({
        title: "Couldn’t save submission",
        description: "Your track was not submitted. Please try again.",
        tone: "error",
      }),
  });

  // Mutation result objects change identity on every render; depending on
  // them made this callback new each time and re-ran the draft hydration
  // effect below on every render. The individual functions are stable.
  const { mutate: evaluateTrack, reset: resetEvaluation } = evaluation;
  const { reset: resetSubmission } = submission;
  const chooseTrack = useCallback(
    (track: Track) => {
      form.setValue("selected", track);
      setConfirmWarnings(false);
      resetEvaluation();
      resetSubmission();
      evaluateTrack(track);
    },
    [evaluateTrack, form, resetEvaluation, resetSubmission],
  );

  // Defer hydration one task so React sees it as a response to the query result,
  // rather than a synchronous state change while committing this render.
  useEffect(() => {
    if (selected || !draft.data?.track) return;
    const track = trackFromInput(draft.data.track);
    const noteFromDraft = draft.data.note ?? "";
    const timer = window.setTimeout(() => {
      chooseTrack(track);
      form.setValue("note", noteFromDraft);
    });
    return () => window.clearTimeout(timer);
  }, [chooseTrack, draft.data, form, selected]);

  useEffect(() => {
    draftPayloadRef.current = { track: selected, note };
  }, [note, selected]);

  useEffect(() => {
    if (!roundId || replaceId || !draft.isSuccess) return;
    const timer = window.setTimeout(() => {
      void put(`/rounds/${roundId}/draft`, {
        track: selected ? asTrackInput(selected) : null,
        note: note || null,
      }).catch(() => {
        showToast({
          title: "Draft not saved",
          description: "Keep this page open and try again before leaving.",
          tone: "error",
        });
      });
    }, 700);
    return () => window.clearTimeout(timer);
  }, [draft.isSuccess, note, replaceId, roundId, selected, showToast]);

  useEffect(() => {
    if (!roundId || replaceId || !draft.isSuccess) return;
    return () => {
      if (submittedRef.current) return;
      const latest = draftPayloadRef.current;
      void put(
        `/rounds/${roundId}/draft`,
        { track: latest.track ? asTrackInput(latest.track) : null, note: latest.note || null },
        { keepalive: true },
      ).catch(() => undefined);
    };
  }, [draft.isSuccess, replaceId, roundId]);

  if (round.isLoading) return <PageSkeleton label="Preparing your submission" variant="detail" />;
  if (round.isError || !round.data)
    return (
      <main className="shell narrow-page-shell">
        <StatePanel kind="error" title="Round unavailable">
          <Link to="/">Return to your rounds</Link>
        </StatePanel>
      </main>
    );
  if (round.data.status !== "open")
    return (
      <main className="shell narrow-page-shell">
        <StatePanel title="This round is not accepting submissions">
          It closes {formatDate(round.data.closesAt)}.{" "}
          <Link to={`/rounds/${roundId}`}>View round</Link>
        </StatePanel>
      </main>
    );

  const mineCount = submissions.data?.filter(
    (entry) => entry.isMine && entry.status === "accepted",
  ).length;
  if (!replaceId && mineCount !== undefined && mineCount >= round.data.submissionLimit)
    return (
      <main className="shell narrow-page-shell">
        <StatePanel title="You’re all set for this round">
          You have used all {round.data.submissionLimit} of your submission
          {round.data.submissionLimit === 1 ? "" : "s"}. You can still change your mind before the
          round closes by managing your submissions.{" "}
          <Link to={`/rounds/${roundId}`}>View round</Link>
        </StatePanel>
      </main>
    );
  const remaining =
    evaluation.data?.limitRemaining ??
    (mineCount === undefined ? undefined : Math.max(0, round.data.submissionLimit - mineCount));
  const policyResults = evaluation.data?.policyResults ?? submission.data?.policyResults ?? [];
  const canSubmit = Boolean(selected && evaluation.data?.canSubmit && !submission.isPending);
  return (
    <main className="shell submission-shell">
      <Link className="back" to={`/rounds/${roundId}`}>
        ← {round.data.title}
      </Link>
      <header className="submission-heading">
        <p className="eyebrow">Your submission</p>
        <h1>{replaceId ? "Replace your track." : "Choose a track."}</h1>
        <p>
          {replaceId
            ? "The new track must pass the same round checks before it replaces your existing submission."
            : remaining === undefined
              ? "Checking how much room you have left in this round."
              : `You have room for ${remaining} more track${remaining === 1 ? "" : "s"} in this round.`}
        </p>
        {round.data.prompt && <p className="round-prompt">Prompt: {round.data.prompt}</p>}
      </header>
      <div className="submission-layout">
        <TrackSearchPanel
          query={query}
          deferredQuery={deferredQuery}
          isSearching={tracks.isFetching}
          hasError={tracks.isError}
          tracks={tracks.data}
          onQueryChange={setQuery}
          onSelect={chooseTrack}
          suggestions={suggestions.data}
          onSuggestion={(suggestion) => setQuery(`${suggestion.artist} ${suggestion.name}`)}
        />
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
          onNoteChange={(value) => form.setValue("note", value)}
          submissionError={submission.isError ? submission.error : null}
          submissionResult={submission.data}
          isSubmitting={submission.isPending}
          canSubmit={canSubmit}
          onSubmit={() => submission.mutate()}
        />
      </div>
      <MobileActionBar label="Submission action">
        <span>
          {selected
            ? canSubmit
              ? "Ready when you are."
              : "Checking this track against the round."
            : "Choose a track to continue."}
        </span>
        <Button
          type="button"
          disabled={
            !canSubmit ||
            (Boolean(evaluation.data?.requiresWarningConfirmation) && !confirmWarnings)
          }
          onClick={() => submission.mutate()}
        >
          {replaceId ? "Replace" : "Submit"}
        </Button>
      </MobileActionBar>
    </main>
  );
}
