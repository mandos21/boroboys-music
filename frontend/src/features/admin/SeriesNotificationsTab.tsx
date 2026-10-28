import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, del, put } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import { Button } from "../../components/ui/button";
import { Disclosure } from "../../components/ui/Disclosure";
import { ConfirmDialog } from "../../components/ui/ConfirmDialog";
import { useToast } from "../../components/ui/ToastProvider";
import { errorMessage } from "./adminUtils";
import type { SeriesDetail } from "./types";
import { NotificationRuleEditor } from "./NotificationRuleEditor";

import {
  notificationTime,
  ruleTiming,
  type NotificationSettings,
  type NotificationRule,
} from "./notificationTypes";

export function SeriesNotificationsTab({
  series,
  active,
}: {
  series: SeriesDetail;
  active: boolean;
}) {
  const queryClient = useQueryClient();
  const key = queryKeys.seriesNotifications(series.id);
  const path = `/admin/series/${series.id}/notifications`;
  const settings = useQuery({
    queryKey: key,
    queryFn: () => api<NotificationSettings>(path),
    enabled: active,
    refetchInterval: active ? 30000 : false,
  });
  const [adding, setAdding] = useState(false);
  const [remove, setRemove] = useState<NotificationRule | null>(null);
  const { showToast } = useToast();
  const refresh = () => queryClient.invalidateQueries({ queryKey: key });
  const removeRule = useMutation({
    mutationFn: (rule: NotificationRule) => del(`${path}/rules/${rule.id}`),
    onSuccess: () => {
      setRemove(null);
      refresh();
      showToast({ title: "Notification rule removed" });
    },
    onError: (error) =>
      showToast({
        title: "Couldn’t remove rule",
        description: errorMessage(error) ?? "Try again.",
        tone: "error",
      }),
  });
  if (settings.isPending)
    return (
      <section className="panel" role="status">
        Loading notifications…
      </section>
    );
  if (!settings.data)
    return (
      <section className="panel">
        <p role="alert">Couldn’t load notifications.</p>
        <Button onClick={() => settings.refetch()}>Try again</Button>
      </section>
    );
  const data = settings.data;
  return (
    <div className="series-tab-stack">
      <NotificationChannels
        key={JSON.stringify(data.channels)}
        channels={data.channels}
        path={path}
        onSaved={refresh}
      />
      <section className="panel">
        <div className="workspace-section-heading">
          <div>
            <h2>Notification rules</h2>
            <p className="field-hint">Choose when to reach your group and what to say.</p>
          </div>
          <Button
            variant="outline"
            disabled={adding || data.rules.length >= 20}
            onClick={() => setAdding(true)}
          >
            Add notification
          </Button>
        </div>
        <p className="field-hint">
          Changes apply to future unsent events in this series. Past events aren’t sent again. Email
          preferences are always respected.
        </p>
        <div className="notification-rules">
          {data.rules.map((rule) => (
            <Disclosure
              keepMounted
              key={rule.id}
              className="notification-rule"
              title={`${rule.name}${rule.enabled ? "" : " · Paused"}`}
              description={`${rule.channel === "email" ? "Email" : "Mattermost"} · ${ruleTiming(rule)}`}
            >
              <NotificationRuleEditor rule={rule} series={series} path={path} onSaved={refresh} />
              <button className="text-button danger" type="button" onClick={() => setRemove(rule)}>
                Remove rule
              </button>
            </Disclosure>
          ))}
          {!data.rules.length && (
            <p>No notification rules yet. Add one to choose a milestone and message.</p>
          )}
          {adding && (
            <section className="notification-rule">
              <h3>New notification</h3>
              <NotificationRuleEditor
                series={series}
                path={path}
                onSaved={() => {
                  setAdding(false);
                  refresh();
                }}
                onCancel={() => setAdding(false)}
              />
            </section>
          )}
        </div>
      </section>
      <section className="panel">
        <h2>Coming up</h2>
        <p className="field-hint">
          Times shown in {data.timezone}. Recipients are checked again before sending.
        </p>
        {!data.upcoming.length && <p>No upcoming notifications for the current rounds.</p>}
        <div className="notification-upcoming">
          {data.upcoming.map((item) => (
            <Disclosure
              keepMounted
              key={`${item.ruleId}:${item.roundId}`}
              title={`${item.ruleName} · ${item.roundTitle}`}
              description={`${notificationTime(item.scheduledAt, data.timezone)} · ${item.channel === "email" ? "Email" : "Mattermost"}${item.channelReady ? "" : " · Channel unavailable"}`}
            >
              <p className="field-hint">{item.audience}</p>
              <p className="notification-message">{item.message}</p>
            </Disclosure>
          ))}
        </div>
      </section>
      <Disclosure
        keepMounted
        className="panel"
        title="Recent deliveries"
        description="The latest 50 events, including retries and skipped notifications."
      >
        {!data.history.length && <p>No notifications have been processed yet.</p>}
        <div className="admin-items">
          {data.history.map((item) => (
            <article key={item.id}>
              <div>
                <strong>
                  {item.ruleName} · {item.roundTitle}
                </strong>
                <span>
                  {notificationTime(item.scheduledAt, data.timezone)} · {item.channel}
                </span>
                {item.detail && <span>{item.detail}</span>}
              </div>
              <span className="notification-delivery-status">
                {item.status} {item.total > 0 && `· ${item.sent}/${item.total} sent`}
              </span>
            </article>
          ))}
        </div>
      </Disclosure>
      <ConfirmDialog
        open={Boolean(remove)}
        title="Remove this notification rule?"
        description="Future sends will stop. Its past delivery history will remain available."
        confirmLabel="Remove rule"
        isPending={removeRule.isPending}
        onOpenChange={(open) => {
          if (!open && !removeRule.isPending) setRemove(null);
        }}
        onConfirm={() => {
          if (remove) removeRule.mutate(remove);
        }}
      />
    </div>
  );
}

function NotificationChannels({
  channels,
  path,
  onSaved,
}: {
  channels: NotificationSettings["channels"];
  path: string;
  onSaved: () => void;
}) {
  const [mode, setMode] = useState(channels.mattermostMode);
  const [webhook, setWebhook] = useState("");
  const { showToast } = useToast();
  const save = useMutation({
    mutationFn: () =>
      put(`${path}/channel`, { mode, ...(webhook.trim() ? { webhook_url: webhook.trim() } : {}) }),
    onSuccess: () => {
      setWebhook("");
      onSaved();
      showToast({ title: "Notification channel saved" });
    },
  });
  return (
    <section className="panel">
      <h2>Delivery channels</h2>
      <div className="notification-channel-summary">
        <p>
          <strong>Email</strong>
          <span>
            {channels.emailReady
              ? "Ready · Members control their own email preferences"
              : "Unavailable · Configure SMTP on the server to enable email"}
          </span>
        </p>
        <p>
          <strong>Mattermost</strong>
          <span>{channels.mattermostReady ? "Connected" : "Not connected"}</span>
        </p>
      </div>
      <Disclosure
        keepMounted
        title="Configure Mattermost"
        description="Use a shared channel or connect a channel for this series."
      >
        <form
          className="admin-round-form"
          onSubmit={(event) => {
            event.preventDefault();
            save.mutate();
          }}
        >
          <label>
            Destination
            <select value={mode} onChange={(event) => setMode(event.target.value as typeof mode)}>
              <option value="disabled">Disabled</option>
              <option value="shared">
                Shared server webhook{channels.sharedMattermostReady ? "" : " (not configured)"}
              </option>
              <option value="custom">Webhook for this series</option>
            </select>
          </label>
          {mode === "custom" && (
            <label>
              Mattermost webhook URL
              <input
                type="password"
                autoComplete="new-password"
                value={webhook}
                onChange={(event) => setWebhook(event.target.value)}
                required={channels.mattermostMode !== "custom"}
                placeholder={
                  channels.mattermostMode === "custom"
                    ? "Saved securely · enter a URL to replace it"
                    : "https://mattermost.example.com/hooks/…"
                }
              />
              <span className="field-hint">
                Create an incoming webhook in Mattermost for the channel you want this series to
                use.
              </span>
            </label>
          )}
          <Button type="submit" disabled={save.isPending}>
            {save.isPending ? "Saving…" : "Save channel"}
          </Button>
          {save.isError && (
            <p className="error-message" role="alert">
              {errorMessage(save.error) ?? "Couldn’t save this channel."}
            </p>
          )}
        </form>
      </Disclosure>
    </section>
  );
}
