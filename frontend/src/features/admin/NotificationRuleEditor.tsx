import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { api, post } from "../../api/client";
import type { components } from "../../api/schema";
import { Button } from "../../components/ui/button";
import { Switch } from "../../components/ui/switch";
import { useToast } from "../../components/ui/ToastProvider";
import { errorMessage } from "./adminUtils";
import {
  MILESTONES,
  notificationTime,
  ruleTiming,
  type NotificationRule,
  type NotificationPreview,
} from "./notificationTypes";
import type { SeriesDetail } from "./types";

type RuleInput = components["schemas"]["RuleInput"];
const NEW_RULE: RuleInput = {
  name: "",
  enabled: true,
  channel: "mattermost",
  milestone: "closes",
  offset_minutes: -1440,
  audience: "members",
  message_template: 'Share your favorites for "{round_title}" before {closes_at}: {round_url}',
};
const FIELDS = ["series_name", "round_title", "round_url", "opens_at", "closes_at", "publishes_at"];

export function NotificationRuleEditor({
  rule,
  series,
  path,
  onSaved,
  onCancel,
}: {
  rule?: NotificationRule;
  series: SeriesDetail;
  path: string;
  onSaved: () => void;
  onCancel?: () => void;
}) {
  const [draft, setDraft] = useState<RuleInput>(rule ?? NEW_RULE);
  const initialMinutes = Math.abs(rule?.offset_minutes ?? -1440);
  const [unit, setUnit] = useState(
    initialMinutes % 1440 === 0 ? 1440 : initialMinutes % 60 === 0 ? 60 : 1,
  );
  const [amount, setAmount] = useState(String(initialMinutes / unit));
  const [direction, setDirection] = useState((rule?.offset_minutes ?? -1440) < 0 ? -1 : 1);
  const [roundId, setRoundId] = useState(
    series.rounds.find((round) => !["published", "cancelled"].includes(round.status))?.id ??
      series.rounds[0]?.id ??
      "",
  );
  const { showToast } = useToast();
  const offset = Number(amount) * unit * direction;
  const canTargetRemaining =
    draft.channel === "email" &&
    ((draft.milestone === "opens" && offset >= 0) || (draft.milestone === "closes" && offset < 0));
  const payload: RuleInput = {
    ...draft,
    offset_minutes: offset,
    audience: canTargetRemaining ? draft.audience : "members",
  };
  const signature = JSON.stringify({ ...payload, round_id: roundId });
  const preview = useMutation({
    mutationFn: () =>
      post<NotificationPreview>(`${path}/preview`, { ...payload, round_id: roundId }).then(
        (data) => ({ data, signature }),
      ),
  });
  const save = useMutation({
    mutationFn: () =>
      rule
        ? api(`${path}/rules/${rule.id}`, { method: "PUT", body: JSON.stringify(payload) })
        : post(`${path}/rules`, payload),
    onSuccess: () => {
      onSaved();
      showToast({ title: "Notification rule saved" });
    },
  });
  const validOffset =
    amount.trim() !== "" &&
    Number.isInteger(offset) &&
    Math.abs(offset) <= 43200 &&
    Number(amount) >= 0;
  return (
    <form
      className="admin-round-form notification-rule-editor"
      onSubmit={(event) => {
        event.preventDefault();
        if (validOffset) save.mutate();
      }}
    >
      <label className="notification-toggle">
        <span>Enabled</span>
        <Switch
          checked={draft.enabled}
          onCheckedChange={(enabled) => setDraft({ ...draft, enabled })}
        />
      </label>
      <div className="notification-form-grid">
        <label>
          Rule name
          <input
            required
            maxLength={100}
            value={draft.name}
            onChange={(event) => setDraft({ ...draft, name: event.target.value })}
          />
        </label>
        <label>
          Send via
          <select
            value={draft.channel}
            onChange={(event) =>
              setDraft({ ...draft, channel: event.target.value as RuleInput["channel"] })
            }
          >
            <option value="mattermost">Mattermost</option>
            <option value="email">Email</option>
          </select>
        </label>
      </div>
      <label>
        Milestone
        <select
          value={draft.milestone}
          onChange={(event) => {
            const milestone = event.target.value as RuleInput["milestone"];
            setDraft({ ...draft, milestone });
            if (milestone === "published") setDirection(1);
          }}
        >
          {Object.entries(MILESTONES).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </label>
      <div className="notification-offset">
        <label>
          How long
          <input
            type="number"
            required
            min="0"
            max={43200 / unit}
            step="1"
            value={amount}
            onChange={(event) => setAmount(event.target.value)}
          />
        </label>
        <label>
          Unit
          <select value={unit} onChange={(event) => setUnit(Number(event.target.value))}>
            <option value={1}>Minutes</option>
            <option value={60}>Hours</option>
            <option value={1440}>Days</option>
          </select>
        </label>
        <label>
          Timing
          <select value={direction} onChange={(event) => setDirection(Number(event.target.value))}>
            <option value={-1} disabled={draft.milestone === "published"}>
              Before
            </option>
            <option value={1}>After</option>
          </select>
        </label>
      </div>
      <p className="field-hint">
        Use 0 to send at the milestone. Maximum 30 days.{" "}
        {draft.milestone === "published"
          ? "This waits for the playlist to publish successfully."
          : draft.milestone === "scheduled_release"
            ? "This uses the planned release time; it does not confirm successful publication."
            : ""}
      </p>
      {draft.channel === "email" && (
        <label>
          Recipients
          <select
            value={payload.audience}
            onChange={(event) =>
              setDraft({ ...draft, audience: event.target.value as RuleInput["audience"] })
            }
          >
            <option value="members">All opted-in round members</option>
            {canTargetRemaining && <option value="remaining">Members who can still submit</option>}
          </select>
          <span className="field-hint">
            {draft.milestone === "published"
              ? "Uses each member’s publication email preference."
              : "Uses each member’s round reminder email preference."}
          </span>
        </label>
      )}
      <label>
        Message
        <textarea
          required
          maxLength={4000}
          rows={4}
          value={draft.message_template}
          onChange={(event) => setDraft({ ...draft, message_template: event.target.value })}
        />
      </label>
      <div className="notification-fields" aria-label="Insert a message field">
        {FIELDS.map((field) => (
          <button
            type="button"
            className="text-button"
            key={field}
            onClick={() =>
              setDraft({ ...draft, message_template: `${draft.message_template} {${field}}` })
            }
          >{`{${field}}`}</button>
        ))}
      </div>
      {series.rounds.length > 0 && (
        <div className="notification-form-grid">
          <label>
            Preview for round
            <select value={roundId} onChange={(event) => setRoundId(event.target.value)}>
              {series.rounds.map((round) => (
                <option key={round.id} value={round.id}>
                  {round.title}
                </option>
              ))}
            </select>
          </label>
          <Button
            variant="outline"
            type="button"
            disabled={
              preview.isPending ||
              !validOffset ||
              !draft.name.trim() ||
              !draft.message_template.trim()
            }
            onClick={() => preview.mutate()}
          >
            {preview.isPending ? "Preparing preview…" : "Preview message"}
          </Button>
        </div>
      )}
      {preview.data?.signature === signature && (
        <div className="notification-preview" role="status">
          <strong>
            {preview.data.data.scheduledAt
              ? notificationTime(preview.data.data.scheduledAt, series.timezone)
              : ruleTiming({ milestone: payload.milestone, offset_minutes: offset })}{" "}
            · {series.timezone}
          </strong>
          <p className="field-hint">
            {preview.data.data.audience}
            {preview.data.data.channelReady ? "" : " · Channel unavailable"}
          </p>
          <p className="notification-message">{preview.data.data.message}</p>
          <small>Preview only. No message has been sent.</small>
        </div>
      )}
      {(save.isError || preview.isError) && (
        <p role="alert" className="error-message">
          {errorMessage(save.error ?? preview.error) ?? "Check the rule and try again."}
        </p>
      )}
      <div className="notification-actions">
        <Button type="submit" disabled={save.isPending || !validOffset}>
          {save.isPending ? "Saving…" : "Save rule"}
        </Button>
        {onCancel && (
          <Button type="button" variant="outline" onClick={onCancel} disabled={save.isPending}>
            Cancel
          </Button>
        )}
      </div>
    </form>
  );
}
