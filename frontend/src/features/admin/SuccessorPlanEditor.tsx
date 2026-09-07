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
  const [calendarDay, setCalendarDay] = useState(
    String(series.roundPlan?.open_day ?? 1),
  );
  const [calendarDuration, setCalendarDuration] = useState(
    String(series.roundPlan?.duration_days ?? 7),
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
                  open_day: Number(calendarDay),
                  duration_days: Number(calendarDuration),
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
            <option value="rolling">Rolling — starts after publication</option>
            <option value="calendar">Calendar — monthly schedule</option>
          </select>
        </label>
        {kind === "rolling" && (
          <label>
            Round duration in hours
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
        {kind === "calendar" && (
          <>
            <label>
              Open on day of month
              <input
                type="number"
                required
                min="1"
                max="28"
                value={calendarDay}
                onChange={(event) => setCalendarDay(event.target.value)}
              />
            </label>
            <label>
              Submission window in days
              <input
                type="number"
                required
                min="1"
                max="366"
                value={calendarDuration}
                onChange={(event) => setCalendarDuration(event.target.value)}
              />
            </label>
          </>
        )}
        <label>
          Successor submission limit (optional)
          <input
            type="number"
            min="0"
            disabled={kind === "none"}
            value={limit}
            onChange={(event) => setLimit(event.target.value)}
          />
        </label>
        <label className="check-label">
          <input
            type="checkbox"
            checked={autoStart}
            disabled={kind === "none"}
            onChange={(event) => setAutoStart(event.target.checked)}
          />
          Start the successor automatically
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
