import { useEffect, useMemo, useState } from "react";
import type { AdminMonthSummary, SubmissionRecord, UserSummary } from "../types";

interface AdminMonthPanelProps {
  summary: AdminMonthSummary | null;
  loading: boolean;
  error: string | null;
  onUpdateSettings: (payload: { submission_limit: number | null; spotify_owner_id: string | null }) => Promise<void>;
  settingsSaving: boolean;
  releaseBusy: boolean;
  onRelease: () => Promise<void>;
  statusMessage: string | null;
  statusError: string | null;
  users: UserSummary[];
}

const formatMonth = (iso: string | undefined) => {
  if (!iso) return "";
  const date = new Date(iso);
  return date.toLocaleString(undefined, { month: "long", year: "numeric" });
};

function AdminMonthPanel({
  summary,
  loading,
  error,
  onUpdateSettings,
  settingsSaving,
  releaseBusy,
  onRelease,
  statusMessage,
  statusError,
  users,
}: AdminMonthPanelProps) {
  const [limitValue, setLimitValue] = useState("");
  const [ownerValue, setOwnerValue] = useState("");
  const [formError, setFormError] = useState<string | null>(null);

  useEffect(() => {
    if (!summary) return;
    setLimitValue(summary.settings.submission_limit != null ? String(summary.settings.submission_limit) : "");
    setOwnerValue(summary.settings.spotify_owner_id ?? "");
  }, [summary]);

  const userLookup = useMemo(() => {
    const map = new Map<number, UserSummary>();
    users.forEach((user) => map.set(user.id, user));
    return map;
  }, [users]);

  const totalSubmissions = summary?.submissions.length ?? 0;
  const submissionLimit = summary?.settings.submission_limit ?? null;
  const limitDisplay = submissionLimit != null ? `${submissionLimit} per person` : "Unlimited per person";

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setFormError(null);

    let parsedLimit: number | null = null;
    const trimmedLimit = limitValue.trim();
    if (trimmedLimit) {
      const parsed = Number(trimmedLimit);
      if (!Number.isFinite(parsed) || parsed < 1) {
        setFormError("Submission limit must be a positive number or left blank for unlimited.");
        return;
      }
      parsedLimit = Math.floor(parsed);
    }

    const trimmedOwner = ownerValue.trim();

    await onUpdateSettings({
      submission_limit: parsedLimit,
      spotify_owner_id: trimmedOwner ? trimmedOwner : null,
    });
  };

  const renderSubmission = (submission: SubmissionRecord) => {
    const user = userLookup.get(submission.user_id);
    const name = user?.display_name?.trim() || user?.username || "Unknown";
    return (
      <li key={submission.id} className="admin-month__submission">
        <div className="admin-month__submission-main">
          <h4>{submission.track.name}</h4>
          <p className="muted">
            {submission.track.artist}
            {submission.track.album ? ` · ${submission.track.album}` : ""}
          </p>
        </div>
        <div className="admin-month__submission-meta">
          <span className="admin-month__submitter">{name}</span>
          {submission.is_locked && <span className="pill pill--locked">Locked</span>}
        </div>
      </li>
    );
  };

  return (
    <section className="card admin-month">
      <div className="card__header">
        <h2>Current Month</h2>
        <span className="muted small">{formatMonth(summary?.settings.month)}</span>
      </div>

      {loading ? (
        <p className="muted">Loading month overview…</p>
      ) : error ? (
        <p className="error">{error}</p>
      ) : summary ? (
        <div className="admin-month__content">
          <form className="admin-month__settings" onSubmit={handleSubmit}>
            <div className="field">
              <label>Submission limit per person</label>
              <input
                type="number"
                min={1}
                step={1}
                value={limitValue}
                onChange={(event) => setLimitValue(event.target.value)}
                placeholder="Unlimited"
              />
              <span className="muted small">Leave blank for unlimited</span>
            </div>
            <div className="field">
              <label>Spotify playlist owner ID</label>
              <input
                type="text"
                value={ownerValue}
                onChange={(event) => setOwnerValue(event.target.value)}
                placeholder="spotify user id"
              />
            </div>
            {formError && <p className="error">{formError}</p>}
            <button className="primary" type="submit" disabled={settingsSaving}>
              {settingsSaving ? "Saving…" : "Save settings"}
            </button>
          </form>

          <div className="admin-month__status">
            <span className="muted small">Limit</span>
            <strong>{limitDisplay}</strong>
            <span className="muted small">Submissions collected</span>
            <strong>{totalSubmissions}</strong>
            {summary.released ? (
              <span className="pill">Released</span>
            ) : (
              <button
                className="secondary"
                type="button"
                onClick={onRelease}
                disabled={releaseBusy || totalSubmissions === 0}
              >
                {releaseBusy ? "Releasing…" : "Release playlist"}
              </button>
            )}
            {statusMessage && <p className="success">{statusMessage}</p>}
            {statusError && <p className="error">{statusError}</p>}
          </div>

          <div className="admin-month__submissions">
            <h3>Submissions</h3>
            {summary.submissions.length === 0 ? (
              <p className="muted">No submissions yet this month.</p>
            ) : (
              <ul className="admin-month__submission-list">
                {summary.submissions.map(renderSubmission)}
              </ul>
            )}
          </div>
        </div>
      ) : (
        <p className="muted">No month data yet.</p>
      )}
    </section>
  );
}

export default AdminMonthPanel;
