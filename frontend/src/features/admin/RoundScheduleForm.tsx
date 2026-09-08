import { useEffect } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Controller, useForm, useWatch } from "react-hook-form";
import { z } from "zod";

import { post } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import { useToast } from "../../components/ui/ToastProvider";
import {
  endOfWallMonth,
  monthTitle,
  nextWallDay,
  toZonedInput,
  zonedInputToIso,
} from "../../lib/time";
import { PolicyEditor } from "./PolicyEditor";
import { errorMessage } from "./adminUtils";
import type { Connection, SeriesDetail, User } from "./types";

/** The wall-clock timestamps are validated against the series timezone, so the
 *  schema is built per render rather than declared once at module scope. */
function scheduleSchema(timezone: string) {
  const wallTime = (label: string) =>
    z
      .string()
      .min(1, `${label} is required.`)
      .refine((value) => zonedInputToIso(value, timezone) !== null, {
        message: `That ${label.toLowerCase()} does not exist in ${timezone}, usually because of daylight saving time.`,
      });
  return z
    .object({
      title: z.string().trim().min(1, "Add a round title.").max(200),
      opensAt: wallTime("Opening time"),
      closesAt: wallTime("Closing time"),
      publishAt: wallTime("Publish time"),
      submissionLimit: z
        .string()
        .refine((v) => /^\d+$/.test(v.trim()), "Use a whole number of submissions."),
      prompt: z.string().max(2000),
      publisherAccountId: z.string(),
      policies: z.array(z.record(z.string(), z.unknown())),
    })
    .refine((v) => zonedInputToIso(v.opensAt, timezone)! < zonedInputToIso(v.closesAt, timezone)!, {
      path: ["closesAt"],
      message: "Closing must come after opening.",
    })
    .refine(
      (v) => zonedInputToIso(v.closesAt, timezone)! <= zonedInputToIso(v.publishAt, timezone)!,
      {
        path: ["publishAt"],
        message: "Publishing cannot come before the round closes.",
      },
    );
}

type ScheduleValues = {
  title: string;
  opensAt: string;
  closesAt: string;
  publishAt: string;
  submissionLimit: string;
  prompt: string;
  publisherAccountId: string;
  policies: Record<string, unknown>[];
};

function suggestedOpening(rounds: SeriesDetail["rounds"], timezone: string) {
  const now = new Date();
  now.setSeconds(0, 0);
  if (!rounds.length) return toZonedInput(now, timezone);
  const latest = [...rounds].sort(
    (first, second) => Date.parse(second.publishAt) - Date.parse(first.publishAt),
  )[0];
  const publishedAt = latest ? new Date(latest.publishAt) : now;
  return toZonedInput(new Date(Math.max(now.getTime(), publishedAt.getTime())), timezone);
}

export function RoundScheduleForm({
  series,
  members,
  spotifyAccounts,
  onScheduled,
}: {
  series: SeriesDetail;
  members: User[];
  spotifyAccounts: Connection[];
  onScheduled: () => void;
}) {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const timezone = series.timezone;
  const monthly = series.roundPlan?.kind === "calendar" && series.roundPlan?.full_month === true;

  const form = useForm<ScheduleValues>({
    resolver: zodResolver(scheduleSchema(timezone)),
    defaultValues: {
      title: "",
      opensAt: suggestedOpening(series.rounds, timezone),
      closesAt: "",
      publishAt: "",
      submissionLimit: "3",
      prompt: "",
      publisherAccountId: "",
      policies: [],
    },
  });
  const { control, formState, handleSubmit, register, reset, setValue } = form;
  // useWatch rather than watch(): the latter cannot be memoized safely, and the
  // React Compiler lint rule rejects it.
  const opensAt = useWatch({ control, name: "opensAt" });
  const closesAt = useWatch({ control, name: "closesAt" });
  const publisherAccountId = useWatch({ control, name: "publisherAccountId" });

  // A monthly series derives the rest of the window from its opening. Only
  // fields the administrator has not touched are derived; `dirtyFields` is what
  // makes that distinction, rather than a hand-kept flag per field.
  useEffect(() => {
    if (!monthly || !opensAt) return;
    if (!formState.dirtyFields.closesAt) setValue("closesAt", endOfWallMonth(opensAt));
    if (!formState.dirtyFields.title) setValue("title", monthTitle(opensAt));
  }, [monthly, opensAt, formState.dirtyFields.closesAt, formState.dirtyFields.title, setValue]);

  useEffect(() => {
    if (!monthly || !closesAt || formState.dirtyFields.publishAt) return;
    setValue("publishAt", nextWallDay(closesAt));
  }, [monthly, closesAt, formState.dirtyFields.publishAt, setValue]);

  const createRound = useMutation({
    mutationFn: (values: ScheduleValues) =>
      post("/admin/rounds", {
        series_id: series.id,
        title: values.title.trim(),
        timezone,
        opens_at: zonedInputToIso(values.opensAt, timezone),
        closes_at: zonedInputToIso(values.closesAt, timezone),
        publish_at: zonedInputToIso(values.publishAt, timezone),
        submission_limit: Number(values.submissionLimit),
        contributor_user_ids: members.map((member) => member.id),
        policy_snapshot: values.policies.length > 0 ? values.policies : undefined,
        prompt: values.prompt.trim() || null,
        publisher_account_id: values.publisherAccountId || null,
      }),
    onSuccess: () => {
      reset({
        title: "",
        opensAt: suggestedOpening(series.rounds, timezone),
        closesAt: "",
        publishAt: "",
        submissionLimit: "3",
        prompt: "",
        publisherAccountId: publisherAccountId,
        policies: [],
      });
      void queryClient.invalidateQueries({ queryKey: queryKeys.adminSeriesDetail(series.id) });
      onScheduled();
      showToast({
        title: "Round scheduled",
        description: "Every current series member will be included.",
      });
    },
    onError: (error) =>
      showToast({
        title: "Couldn’t schedule round",
        description: errorMessage(error) ?? "Check the schedule and try again.",
        tone: "error",
      }),
  });

  const fieldError = (name: keyof ScheduleValues) => formState.errors[name]?.message;

  return (
    <section className="panel" id="rounds">
      <h2>Schedule a round</h2>
      <form
        className="admin-round-form"
        noValidate
        onSubmit={handleSubmit((values) => createRound.mutate(values))}
      >
        <label>
          Title
          <input {...register("title")} maxLength={200} />
          {fieldError("title") && <span className="error-message">{fieldError("title")}</span>}
        </label>
        <label>
          Opens
          <input type="datetime-local" {...register("opensAt")} />
          <span className="field-hint">
            Times use {timezone}. Defaults to now, unless the latest round publishes later.
          </span>
          {fieldError("opensAt") && <span className="error-message">{fieldError("opensAt")}</span>}
        </label>
        <label>
          Closes
          <input type="datetime-local" min={opensAt || undefined} {...register("closesAt")} />
          {fieldError("closesAt") && (
            <span className="error-message">{fieldError("closesAt")}</span>
          )}
        </label>
        <label>
          Publishes
          <input type="datetime-local" min={closesAt || undefined} {...register("publishAt")} />
          {fieldError("publishAt") && (
            <span className="error-message">{fieldError("publishAt")}</span>
          )}
        </label>
        <label>
          Submissions per contributor
          <input type="number" min="0" {...register("submissionLimit")} />
          {fieldError("submissionLimit") && (
            <span className="error-message">{fieldError("submissionLimit")}</span>
          )}
        </label>
        <label>
          Prompt <span className="field-hint">Optional</span>
          <textarea
            {...register("prompt")}
            maxLength={2000}
            placeholder="A theme, question, or loose idea for this round."
          />
        </label>
        <label>
          Publishing account <span className="field-hint">Optional</span>
          <select {...register("publisherAccountId")}>
            <option value="">Release this round by hand</option>
            {spotifyAccounts.map((account) => (
              <option key={account.id} value={account.id}>
                {account.displayName ?? "Spotify account"}
              </option>
            ))}
          </select>
          <span className="field-hint">
            {publisherAccountId
              ? "This round releases itself at its publish time."
              : "Without an account, somebody has to publish the round once it closes."}
            {spotifyAccounts.length === 0
              ? " Link a Spotify account on your profile to enable this."
              : ""}
          </span>
        </label>
        <p className="field-hint">
          {members.length
            ? `${members.length} current series member${members.length === 1 ? "" : "s"} will be included.`
            : "Add members before scheduling this round."}
        </p>
        <Controller
          control={control}
          name="policies"
          render={({ field }) => <PolicyEditor value={field.value} onChange={field.onChange} />}
        />
        <button className="button" disabled={createRound.isPending || members.length === 0}>
          {createRound.isPending ? "Scheduling…" : "Schedule round"}
        </button>
        {errorMessage(createRound.error) && (
          <p className="error-message" role="alert">
            {errorMessage(createRound.error)}
          </p>
        )}
      </form>
    </section>
  );
}
