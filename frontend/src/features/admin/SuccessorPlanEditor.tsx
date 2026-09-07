import { useState } from "react";
import { useMutation } from "@tanstack/react-query";

import { patch } from "../../api/client";
import { useToast } from "../../components/ui/ToastProvider";
import { errorMessage } from "./adminUtils";
import type { Series } from "./types";

export function SuccessorPlanEditor({
  series,
  onSaved,
}: {
  series: Series;
  onSaved: () => void;
}) {
  const { showToast } = useToast();
  const initialKind =
    series.roundPlan?.kind === "rolling" ||
    series.roundPlan?.kind === "calendar"
      ? series.roundPlan.kind
      : "none";
  const [kind, setKind] = useState<"none" | "rolling" | "calendar">(
    initialKind,
  );
  const [rollingHours, setRollingHours] = useState(
    String(series.roundPlan?.duration_hours ?? ""),
  );
  const [limit, setLimit] = useState(
    String(series.roundPlan?.submission_limit ?? ""),
  );
  const [autoStart, setAutoStart] = useState(series.autoStartNextRound);
  const save = useMutation({
    mutationFn: () =>
      patch(`/admin/series/${series.id}`, {
        auto_start_next_round: kind === "none" ? false : autoStart,
        round_plan:
          kind === "rolling"
            ? {
                kind: "rolling",
                duration_hours: Number(rollingHours),
                submission_limit: limit ? Number(limit) : null,
              }
            : kind === "calendar"
              ? {
                  kind: "calendar",
                  open_day: 1,
                  duration_days: 1,
                  full_month: true,
                  submission_limit: limit ? Number(limit) : null,
                }
              : null,
      }),
    onSuccess: () => {
      onSaved();
      showToast({ title: "Automation saved", description: "Future successors will follow this plan after a successful publication." });
    },
    onError: () => showToast({ title: "Couldn’t save automation", description: "Check the plan and try again.", tone: "error" }),
  });
  return (
    <section className="panel">
      <h2>Automatic next round</h2>
      <p>
        Changing this affects only successors created after a successful
        publication.
      </p>
      <form
        className="admin-round-form"
        onSubmit={(event) => {
          event.preventDefault();
          save.mutate();
        }}
      >
        <label>
          Timeline
          <select
            value={kind}
            onChange={(event) =>
              setKind(event.target.value as "none" | "rolling" | "calendar")
            }
          >
            <option value="none">None — schedule rounds manually</option>
            <option value="rolling">Rolling — a continuous duration after publication</option>
            <option value="calendar">Monthly — first through last day of each month</option>
          </select>
        </label>
        {kind === "rolling" && (
          <label>
            How long should each rolling round stay open? (hours)
            <input
              type="number"
              required
              min="1"
              max="8760"
              value={rollingHours}
              onChange={(event) => setRollingHours(event.target.value)}
            />
          </label>
        )}
        {kind === "rolling" && <p className="field-hint">The next round opens as soon as the previous playlist is published, then releases when this duration ends.</p>}
        {kind === "calendar" && <p className="field-hint">Each successor opens on the first, accepts submissions through the end of that month, and publishes the following day.</p>}
        <label>
          Tracks each contributor can submit in future rounds (optional)
          <input
            type="number"
            min="0"
            disabled={kind === "none"}
            value={limit}
            onChange={(event) => setLimit(event.target.value)}
          />
          <span className="field-hint">Leave blank to reuse the submission limit from the round that was just published.</span>
        </label>
        <label className="check-label">
          <input
            type="checkbox"
            checked={autoStart}
            disabled={kind === "none"}
            onChange={(event) => setAutoStart(event.target.checked)}
          />
          Create the next round automatically when this one is published
        </label>
        <button className="button" disabled={save.isPending}>
          {save.isPending ? "Saving…" : "Save plan"}
        </button>
        {errorMessage(save.error) && (
          <p className="error-message" role="alert">
            {errorMessage(save.error)}
          </p>
        )}
      </form>
    </section>
  );
}
