import { formatDate } from "../../lib/format";
import { InfoHint } from "../../components/ui/InfoHint";
import { Button } from "../../components/ui/button";

import type { Evidence, PolicyResult, SubmissionResult, Track } from "./types";

type SubmissionReviewPanelProps = {
  selected: Track | null;
  isEvaluating: boolean;
  evaluationFailed: boolean;
  policyResults: PolicyResult[];
  isLoadingEvidence: boolean;
  evidence: Evidence | undefined;
  requiresWarningConfirmation: boolean;
  confirmWarnings: boolean;
  onConfirmWarningsChange: (value: boolean) => void;
  isReplacing: boolean;
  note: string;
  onNoteChange: (value: string) => void;
  submissionError: Error | null;
  submissionResult: SubmissionResult | undefined;
  isSubmitting: boolean;
  canSubmit: boolean;
  onSubmit: () => void;
};

export function SubmissionReviewPanel({
  selected,
  isEvaluating,
  evaluationFailed,
  policyResults,
  isLoadingEvidence,
  evidence,
  requiresWarningConfirmation,
  confirmWarnings,
  onConfirmWarningsChange,
  isReplacing,
  note,
  onNoteChange,
  submissionError,
  submissionResult,
  isSubmitting,
  canSubmit,
  onSubmit,
}: SubmissionReviewPanelProps) {
  return (
    <section className="panel review-panel" aria-live="polite" aria-label="Review your submission">
      <h2>Review</h2>
      {!selected && <p>Select a Spotify track to check it against this round&apos;s rules.</p>}
      {selected && (
        <div className="selected-track">
          {selected.artworkUrl ? (
            <img src={selected.artworkUrl} alt="" />
          ) : (
            <span className="cover-placeholder" aria-hidden="true">
              ♫
            </span>
          )}
          <div>
            <h3>{selected.name}</h3>
            <p>
              {selected.artist}
              {selected.album ? ` · ${selected.album}` : ""}
            </p>
          </div>
        </div>
      )}
      {isEvaluating && <p role="status">Checking rules and listening evidence…</p>}
      {evaluationFailed && (
        <p className="error-message" role="alert">
          The track could not be evaluated. Try selecting it again.
        </p>
      )}
      {policyResults.length > 0 && (
        <div className="policy-results">
          <h3>Round checks</h3>
          {policyResults.map((result) => (
            <p
              className={`policy ${result.decision}${result.kind === "previously_submitted" ? " history" : ""}`}
              key={`${result.kind}-${result.message}`}
            >
              {result.message}
            </p>
          ))}
        </div>
      )}
      {isLoadingEvidence && (
        <p className="field-hint" role="status">
          Checking for newer Last.fm listens…
        </p>
      )}
      {evidence && (
        <div className="evidence">
          <h3>Group listening evidence</h3>
          <InfoHint label="How listening evidence works">
            These are cached all-time listens from linked Last.fm accounts, not submissions to this
            series. Recent plays can take a moment to appear. Previous submissions are checked
            separately under Round checks.
          </InfoHint>
          <p className="evidence-explainer">
            Cached Last.fm listens; previous submissions are checked separately.
          </p>
          {evidence.evidence.length === 0 ? (
            <p className="field-hint">
              No shared Last.fm evidence is cached yet. It will refresh in the background.
            </p>
          ) : (
            <div className="evidence-list">
              {evidence.evidence.map((item) => (
                <p key={item.accountId}>
                  <strong>{item.isMine ? "You" : (item.displayName ?? "A contributor")}</strong>:
                  track {item.playcount ?? "—"} · artist {item.artistPlaycount ?? "—"}
                  {item.albumPlaycount !== null ? ` · album ${item.albumPlaycount}` : ""}{" "}
                  <small>observed {formatDate(item.fetchedAt)}</small>
                </p>
              ))}
            </div>
          )}
        </div>
      )}
      {requiresWarningConfirmation && (
        <label className="confirmation">
          <input
            type="checkbox"
            checked={confirmWarnings}
            onChange={(event) => onConfirmWarningsChange(event.target.checked)}
          />
          I understand the warning and want to submit this track.
        </label>
      )}
      {!isReplacing ? (
        <>
          <label className="note-label" htmlFor="submission-note">
            Optional note
          </label>
          <p className="field-hint">
            Tell the group what makes this track a favorite. Your note appears with it when the
            playlist is released.
          </p>
          <textarea
            id="submission-note"
            value={note}
            maxLength={4000}
            onChange={(event) => onNoteChange(event.target.value)}
            placeholder="What did you love about this track?"
          />
        </>
      ) : (
        <p className="field-hint">
          Your existing note is preserved. You can edit it from the round page.
        </p>
      )}
      {submissionError && (
        <p className="error-message" role="alert">
          {submissionError.message}
        </p>
      )}
      {submissionResult && !submissionResult.accepted && (
        <p className="error-message" role="alert">
          {submissionResult.requiresWarningConfirmation
            ? "Confirm the warning before submitting."
            : "This track cannot be submitted under the current rules."}
        </p>
      )}
      <Button
        className="submission-submit"
        type="button"
        disabled={!canSubmit || (requiresWarningConfirmation && !confirmWarnings)}
        onClick={onSubmit}
      >
        {isSubmitting ? "Submitting…" : isReplacing ? "Replace track" : "Submit track"}
      </Button>
    </section>
  );
}
