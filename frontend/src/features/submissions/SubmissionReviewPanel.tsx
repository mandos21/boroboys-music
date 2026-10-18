import { Link } from "react-router";
import { InfoHint } from "../../components/ui/InfoHint";
import { Button } from "../../components/ui/button";

import type { Evidence, PolicyResult, SubmissionResult, Track } from "./types";

type SubmissionReviewPanelProps = {
  selected: Track | null;
  isEvaluating: boolean;
  evaluationFailed: boolean;
  policyResults: PolicyResult[];
  isLoadingEvidence: boolean;
  evidenceFailed: boolean;
  evidence: Evidence | undefined;
  hasLastfmConnection: boolean | undefined;
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
  evidenceFailed,
  evidence,
  hasLastfmConnection,
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
  const warnings = policyResults.filter((result) => result.decision === "warn");
  const otherResults = policyResults.filter((result) => result.decision !== "warn");
  const otherListeners =
    evidence?.evidence.filter((item) => !item.isMine && (item.playcount ?? 0) > 0).length ?? 0;
  const ownListens = evidence?.evidence.some((item) => item.isMine && (item.playcount ?? 0) > 0);

  return (
    <section className="panel review-panel" aria-label="Review your submission">
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
          {otherResults.map((result) => (
            <p
              className={`policy ${result.decision}${result.kind === "previously_submitted" ? " history" : ""}`}
              key={`${result.kind}-${result.message}`}
            >
              {result.message}
            </p>
          ))}
          {warnings.length > 0 && (
            <div className="policy-warning">
              <strong>Worth a second look</strong>
              {warnings.map((result) => (
                <p key={`${result.kind}-${result.message}`}>{result.message}</p>
              ))}
              {requiresWarningConfirmation && (
                <label className="confirmation">
                  <input
                    type="checkbox"
                    checked={confirmWarnings}
                    onChange={(event) => onConfirmWarningsChange(event.target.checked)}
                  />
                  <span>
                    I understand and still want to submit this track.
                    <small>
                      Generally, do this only if you have a good reason, such as an end-of-year
                      playlist.
                    </small>
                  </span>
                </label>
              )}
            </div>
          )}
        </div>
      )}
      {selected && (
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
          {evidence && evidence.evidence.length > 0 && (
            <p className="evidence-summary">
              {otherListeners > 0
                ? `This may be familiar to ${otherListeners} other ${otherListeners === 1 ? "person" : "people"} in the round.`
                : ownListens
                  ? "You’ve listened to this track before. No other shared track listens appear yet."
                  : "No shared track listens appear yet. It may still be familiar to someone."}
            </p>
          )}
          {evidence && evidence.evidence.length > 0 ? (
            <ul className="evidence-list">
              {evidence.evidence.map((item) => (
                <li key={item.accountId}>
                  <strong className="evidence-person">
                    {item.isMine ? "You" : (item.displayName ?? "A contributor")}
                  </strong>
                  <span className="evidence-counts">
                    <span>
                      Track <strong>{item.playcount ?? "—"}</strong>
                    </span>
                    <span>
                      Artist <strong>{item.artistPlaycount ?? "—"}</strong>
                    </span>
                    <span>
                      Album <strong>{item.albumPlaycount ?? "—"}</strong>
                    </span>
                  </span>
                </li>
              ))}
            </ul>
          ) : evidence && !isLoadingEvidence ? (
            <p className="field-hint">
              No shared Last.fm listening data is available for this track yet.
            </p>
          ) : null}
          {isLoadingEvidence && (
            <p className="evidence-refresh" role="status">
              Checking for recent Last.fm listens…
            </p>
          )}
          {evidenceFailed && (
            <p className="field-hint" role="status">
              Couldn’t load listening data right now. You can still submit your track.
            </p>
          )}
          {hasLastfmConnection === false && (
            <p className="evidence-connect">
              Have a Last.fm account? <Link to="/settings">Link it in settings</Link> so other
              contributors can see your listening data while choosing tracks.
            </p>
          )}
        </div>
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
