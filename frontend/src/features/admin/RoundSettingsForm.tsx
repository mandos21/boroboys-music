import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation } from "@tanstack/react-query";
import { useForm, useWatch } from "react-hook-form";
import { z } from "zod";

import { patch } from "../../api/client";
import { useToast } from "../../components/ui/ToastProvider";
import { toZonedInput, zonedInputToIso } from "../../lib/time";
import { errorMessage } from "./adminUtils";
import type { AdminRound, Connection } from "./types";

type SettingsValues = {
  title: string;
  opensAt: string;
  closesAt: string;
  publishAt: string;
  submissionLimit: string;
  prompt: string;
  publisherAccountId: string;
};

function settingsSchema(timezone: string) {
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
        .refine((value) => /^\d+$/.test(value.trim()), "Use a whole number of submissions."),
      prompt: z.string().max(2000),
      publisherAccountId: z.string(),
    })
    .refine(
      (value) =>
        zonedInputToIso(value.opensAt, timezone)! < zonedInputToIso(value.closesAt, timezone)!,
      {
        path: ["closesAt"],
        message: "Closing must come after opening.",
      },
    )
    .refine(
      (value) =>
        zonedInputToIso(value.closesAt, timezone)! <= zonedInputToIso(value.publishAt, timezone)!,
      { path: ["publishAt"], message: "Publishing cannot come before the round closes." },
    );
}

function valuesFor(round: AdminRound): SettingsValues {
  return {
    title: round.title,
    opensAt: toZonedInput(round.opensAt, round.timezone),
    closesAt: toZonedInput(round.closesAt, round.timezone),
    publishAt: toZonedInput(round.publishAt, round.timezone),
    submissionLimit: String(round.submissionLimit),
    prompt: round.prompt ?? "",
    publisherAccountId: round.publisherAccountId ?? "",
  };
}

export function RoundSettingsForm({
  round,
  spotifyAccounts,
  onSaved,
}: {
  round: AdminRound;
  spotifyAccounts: Connection[];
  onSaved: () => void;
}) {
  const { showToast } = useToast();
  const openingEditable = ["draft", "scheduled"].includes(round.status);
  const form = useForm<SettingsValues>({
    resolver: zodResolver(settingsSchema(round.timezone)),
    defaultValues: valuesFor(round),
  });
  const { formState, handleSubmit, register } = form;
  const opensAt = useWatch({ control: form.control, name: "opensAt" });
  const closesAt = useWatch({ control: form.control, name: "closesAt" });
  const publisherAccountId = useWatch({ control: form.control, name: "publisherAccountId" });
  const saveRound = useMutation({
    mutationFn: (values: SettingsValues) =>
      patch(`/admin/rounds/${round.id}`, {
        title: values.title.trim(),
        ...(openingEditable ? { opens_at: zonedInputToIso(values.opensAt, round.timezone) } : {}),
        closes_at: zonedInputToIso(values.closesAt, round.timezone),
        publish_at: zonedInputToIso(values.publishAt, round.timezone),
        submission_limit: Number(values.submissionLimit),
        prompt: values.prompt.trim() || null,
        publisher_account_id: values.publisherAccountId || null,
      }),
    onSuccess: () => {
      onSaved();
      showToast({
        title: "Round settings saved",
        description: "The schedule and submission limit are updated.",
      });
    },
    onError: (error) =>
      showToast({
        title: "Couldn’t save round settings",
        description: errorMessage(error) ?? "Try again in a moment.",
        tone: "error",
      }),
  });
  const error = (name: keyof SettingsValues) => formState.errors[name]?.message;

  return (
    <form
      className="admin-round-form"
      noValidate
      onSubmit={handleSubmit((values) => saveRound.mutate(values))}
    >
      <label>
        Title
        <input maxLength={200} {...register("title")} />
        {error("title") && <span className="error-message">{error("title")}</span>}
      </label>
      <label>
        Opens
        <input type="datetime-local" disabled={!openingEditable} {...register("opensAt")} />
        <span className="field-hint">
          Times use {round.timezone}.
          {!openingEditable ? " An open round keeps its original opening time." : ""}
        </span>
        {error("opensAt") && <span className="error-message">{error("opensAt")}</span>}
      </label>
      <label>
        Closes
        <input type="datetime-local" min={opensAt || undefined} {...register("closesAt")} />
        {error("closesAt") && <span className="error-message">{error("closesAt")}</span>}
      </label>
      <label>
        Publishes
        <input type="datetime-local" min={closesAt || undefined} {...register("publishAt")} />
        {error("publishAt") && <span className="error-message">{error("publishAt")}</span>}
      </label>
      <label>
        Submissions per contributor
        <input type="number" min="0" {...register("submissionLimit")} />
        {error("submissionLimit") && (
          <span className="error-message">{error("submissionLimit")}</span>
        )}
      </label>
      <label>
        Prompt <span className="field-hint">Optional</span>
        <textarea
          maxLength={2000}
          placeholder="A theme, question, or loose idea for this round."
          {...register("prompt")}
        />
        {error("prompt") && <span className="error-message">{error("prompt")}</span>}
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
            ? "This round releases itself at its publish time, through this Spotify account."
            : "Without an account, the round stays closed until somebody publishes it."}
          {spotifyAccounts.length === 0
            ? " Link a Spotify account on your profile to enable this."
            : ""}
        </span>
      </label>
      <button className="button" disabled={saveRound.isPending}>
        {saveRound.isPending ? "Saving…" : "Save round settings"}
      </button>
      {errorMessage(saveRound.error) && (
        <p className="error-message" role="alert">
          {errorMessage(saveRound.error)}
        </p>
      )}
    </form>
  );
}
