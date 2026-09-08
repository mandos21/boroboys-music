import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation } from "@tanstack/react-query";
import { useForm, useWatch } from "react-hook-form";
import { z } from "zod";

import { patch } from "../../api/client";
import { useToast } from "../../components/ui/ToastProvider";
import { errorMessage } from "./adminUtils";
import type { Series } from "./types";

const planSchema = z
  .object({
    kind: z.enum(["none", "rolling", "calendar"]),
    rollingDays: z.string(),
    limit: z.string(),
    autoStart: z.boolean(),
  })
  .superRefine((value, context) => {
    if (value.kind === "rolling" && !/^[1-9]\d*$/.test(value.rollingDays)) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["rollingDays"],
        message: "Use a whole number of days.",
      });
    }
    if (value.limit && !/^\d+$/.test(value.limit)) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["limit"],
        message: "Use a whole number of tracks.",
      });
    }
  });

type PlanValues = z.infer<typeof planSchema>;

function defaults(series: Series): PlanValues {
  const initialKind =
    series.roundPlan?.kind === "rolling" || series.roundPlan?.kind === "calendar"
      ? series.roundPlan.kind
      : "none";
  const legacyDurationHours = Number(series.roundPlan?.duration_hours ?? 0);
  const legacyDurationDays =
    legacyDurationHours > 0 ? Math.max(1, Math.round(legacyDurationHours / 24)) : "";
  return {
    kind: initialKind,
    rollingDays: String(series.roundPlan?.duration_days ?? legacyDurationDays),
    limit: String(series.roundPlan?.submission_limit ?? ""),
    autoStart: series.autoStartNextRound,
  };
}

export function SuccessorPlanEditor({ series, onSaved }: { series: Series; onSaved: () => void }) {
  const { showToast } = useToast();
  const form = useForm<PlanValues>({
    resolver: zodResolver(planSchema),
    defaultValues: defaults(series),
  });
  const { formState, handleSubmit, register } = form;
  const kind = useWatch({ control: form.control, name: "kind" });
  const save = useMutation({
    mutationFn: (values: PlanValues) =>
      patch(`/admin/series/${series.id}`, {
        auto_start_next_round: values.kind === "none" ? false : values.autoStart,
        round_plan:
          values.kind === "rolling"
            ? {
                kind: "rolling",
                duration_days: Number(values.rollingDays),
                submission_limit: values.limit ? Number(values.limit) : null,
              }
            : values.kind === "calendar"
              ? {
                  kind: "calendar",
                  open_day: 1,
                  duration_days: 1,
                  full_month: true,
                  submission_limit: values.limit ? Number(values.limit) : null,
                }
              : null,
      }),
    onSuccess: () => {
      onSaved();
      showToast({
        title: "Automation saved",
        description: "Future successors will follow this plan after a successful publication.",
      });
    },
    onError: () =>
      showToast({
        title: "Couldn’t save automation",
        description: "Check the plan and try again.",
        tone: "error",
      }),
  });
  const error = (name: keyof PlanValues) => formState.errors[name]?.message;

  return (
    <section className="panel">
      <h2>Automatic next round</h2>
      <p>Changing this affects only successors created after a successful publication.</p>
      <form
        className="admin-round-form"
        noValidate
        onSubmit={handleSubmit((values) => save.mutate(values))}
      >
        <label>
          Timeline
          <select {...register("kind")}>
            <option value="none">None — schedule rounds manually</option>
            <option value="rolling">Rolling — a continuous duration after publication</option>
            <option value="calendar">Monthly — first through last day of each month</option>
          </select>
        </label>
        {kind === "rolling" && (
          <label>
            How many days should each rolling round stay open?
            <input type="number" min="1" max="365" {...register("rollingDays")} />
            {error("rollingDays") && <span className="error-message">{error("rollingDays")}</span>}
          </label>
        )}
        {kind === "rolling" && (
          <p className="field-hint">
            Use this for an ongoing cadence rather than a calendar date. The next round opens when
            the previous playlist is published, stays open for this many days, then releases. A
            delayed release shifts the next round with it.
          </p>
        )}
        {kind === "calendar" && (
          <p className="field-hint">
            Each successor opens on the first, accepts submissions through the end of that month,
            and publishes the following day.
          </p>
        )}
        <label>
          Tracks each contributor can submit in future rounds (optional)
          <input type="number" min="0" disabled={kind === "none"} {...register("limit")} />
          <span className="field-hint">
            Leave blank to reuse the submission limit from the round that was just published.
          </span>
          {error("limit") && <span className="error-message">{error("limit")}</span>}
        </label>
        <label className="check-label">
          <input type="checkbox" disabled={kind === "none"} {...register("autoStart")} />
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
