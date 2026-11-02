import { BellOff } from "lucide-react";
import { useEffect, useId, useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, ApiError, patch } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import type { components } from "../../api/schema";
import { Disclosure } from "../../components/ui/Disclosure";
import { StatePanel } from "../../components/ui/StatePanel";
import { useToast } from "../../components/ui/ToastProvider";
import { Switch } from "../../components/ui/switch";
import "./notification-settings.css";

type NotificationSettings = components["schemas"]["NotificationSettingsResponse"];
type SeriesSettings = components["schemas"]["SeriesNotificationSettingsResponse"];
type NotificationSettingsUpdate = components["schemas"]["NotificationSettingsUpdate"];

const TOGGLES: {
  key: keyof NotificationSettings;
  requestKey: keyof NotificationSettingsUpdate;
  label: string;
  description: string;
}[] = [
  {
    key: "notifyReminderEmails",
    requestKey: "notify_reminder_emails",
    label: "Round reminders",
    description: "Reminders and announcements scheduled by your series administrators.",
  },
  {
    key: "notifyRoundPublishedEmails",
    requestKey: "notify_round_published_emails",
    label: "Round published",
    description: "An email once a round you're in is published as a playlist.",
  },
];

function PreferenceSwitches({
  values,
  global,
  pending,
  compact = false,
  onChange,
}: {
  values: NotificationSettings;
  global?: NotificationSettings;
  pending: boolean;
  compact?: boolean;
  onChange: (change: NotificationSettingsUpdate) => void;
}) {
  const descriptionId = useId();
  return (
    <div className="notification-settings">
      {TOGGLES.map(({ key, requestKey, label, description }) => {
        const blocked = global?.[key] === false;
        return (
          <label className="notification-toggle" key={key}>
            <span>
              <span className="notification-toggle-label" id={`${descriptionId}-${key}-label`}>
                {label}
              </span>
              <span className="notification-toggle-description" id={`${descriptionId}-${key}`}>
                {blocked
                  ? compact
                    ? "Off in your global email settings."
                    : `${key === "notifyReminderEmails" ? "Round reminders" : "Publication emails"} are turned off for all series. Your choice for this series is saved.`
                  : description}
              </span>
            </span>
            <Switch
              aria-labelledby={`${descriptionId}-${key}-label`}
              aria-describedby={`${descriptionId}-${key}`}
              checked={!blocked && values[key]}
              onCheckedChange={(checked) => onChange({ [requestKey]: checked })}
              disabled={pending || blocked}
            />
          </label>
        );
      })}
    </div>
  );
}

/** Global controls and the per-series list; the series page uses the same controls in a dialog. */
export function NotificationSettingsPanel({
  seriesId,
  selectedSeriesId,
}: {
  seriesId?: string;
  selectedSeriesId?: string | null;
}) {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const selectedRow = useRef<HTMLDivElement>(null);
  const settings = useQuery({
    queryKey: queryKeys.notificationSettings(),
    queryFn: () => api<NotificationSettings>("/profiles/me/notification-settings"),
    retry: false,
  });
  const series = useQuery({
    queryKey: queryKeys.seriesEmailPreferences(),
    queryFn: () => api<SeriesSettings[]>("/profiles/me/notification-settings/series"),
    enabled: settings.isSuccess,
    retry: false,
  });
  const onError = () =>
    showToast({
      title: "Couldn’t save notification setting",
      description: "We couldn’t confirm this change. Try again in a moment.",
      tone: "error",
    });
  const update = useMutation({
    mutationFn: (change: NotificationSettingsUpdate) =>
      patch<NotificationSettings>("/profiles/me/notification-settings", change),
    onMutate: () => queryClient.cancelQueries({ queryKey: queryKeys.notificationSettings() }),
    onSuccess: async (data) => {
      await queryClient.cancelQueries({ queryKey: queryKeys.notificationSettings() });
      queryClient.setQueryData(queryKeys.notificationSettings(), data);
      void queryClient.invalidateQueries({ queryKey: queryKeys.seriesEmailPreferences() });
    },
    onError,
  });
  const updateSeries = useMutation({
    mutationFn: ({ id, change }: { id: string; change: NotificationSettingsUpdate }) =>
      patch<SeriesSettings>(`/profiles/me/notification-settings/series/${id}`, change),
    onMutate: () => queryClient.cancelQueries({ queryKey: queryKeys.seriesEmailPreferences() }),
    onSuccess: async (data) => {
      await queryClient.cancelQueries({ queryKey: queryKeys.seriesEmailPreferences() });
      queryClient.setQueryData<SeriesSettings[]>(queryKeys.seriesEmailPreferences(), (previous) =>
        previous?.map((item) => (item.seriesId === data.seriesId ? data : item)),
      );
    },
    onError,
  });
  const selectedLoaded = series.data?.some((item) => item.seriesId === selectedSeriesId);
  useEffect(() => {
    if (selectedLoaded) selectedRow.current?.scrollIntoView?.({ block: "center" });
  }, [selectedSeriesId, selectedLoaded]);

  if (settings.isLoading) {
    return (
      <StatePanel kind="loading" title="Checking your notification settings">
        Looking for your saved preferences.
      </StatePanel>
    );
  }
  if (settings.error instanceof ApiError && settings.error.status === 401) {
    const returnPath = window.location.pathname + window.location.search + window.location.hash;
    return (
      <StatePanel title="Sign in to manage your email preferences">
        <a href={`/api/v1/auth/login?return=${encodeURIComponent(returnPath)}`}>Sign in</a> to
        choose which emails you receive.
      </StatePanel>
    );
  }
  if (settings.isError || !settings.data) {
    return (
      <StatePanel kind="error" title="We couldn’t load your notification settings">
        Please refresh the page and try again.
      </StatePanel>
    );
  }
  const global = settings.data;
  const items = series.data?.filter((item) => !seriesId || item.seriesId === seriesId);
  const pending = update.isPending || updateSeries.isPending;
  return (
    <div className="email-preferences">
      {!seriesId && (
        <section aria-label="Across all series">
          <h3>Across all series</h3>
          <p className="muted">Turn off a category here to stop those emails from every series.</p>
          <PreferenceSwitches values={global} pending={pending} onChange={update.mutate} />
        </section>
      )}
      <section aria-label={seriesId ? "Emails for this series" : "Your series"}>
        {!seriesId && <h3>Your series</h3>}
        <p className="muted">
          {seriesId
            ? "Choose the emails you receive from this series, now and in future rounds."
            : "Choose which series you hear from. These choices carry over to future rounds. Shared Mattermost messages are unaffected."}
        </p>
        {seriesId && (!global.notifyReminderEmails || !global.notifyRoundPublishedEmails) && (
          <div className="email-global-notice" role="status">
            <BellOff aria-hidden="true" size={20} />
            <div>
              <strong>
                {!global.notifyReminderEmails && !global.notifyRoundPublishedEmails
                  ? "Email notifications are off globally"
                  : !global.notifyReminderEmails
                    ? "Round reminders are off globally"
                    : "Publication emails are off globally"}
              </strong>
              <p>
                Enable them in your global settings to receive these emails. Your choices for this
                series are saved.
              </p>
            </div>
          </div>
        )}
        {series.isLoading && <p role="status">Loading your series…</p>}
        {series.isError && (
          <StatePanel kind="error" title="We couldn’t load your series preferences">
            Please refresh the page and try again.
          </StatePanel>
        )}
        {items?.length === 0 && (
          <p>
            {seriesId
              ? "This series is no longer available to you."
              : "Your series will appear here when you join one."}
          </p>
        )}
        {!seriesId && selectedSeriesId && series.isSuccess && !selectedLoaded && (
          <p role="status">The series from this link is no longer available to you.</p>
        )}
        <div className="series-email-preferences">
          {items?.map((item) => {
            const controls = (
              <PreferenceSwitches
                values={item}
                global={global}
                compact={Boolean(seriesId)}
                pending={pending}
                onChange={(change) => updateSeries.mutate({ id: item.seriesId, change })}
              />
            );
            return seriesId ? (
              <div key={item.seriesId}>{controls}</div>
            ) : (
              <div
                key={`${item.seriesId}-${item.seriesId === selectedSeriesId}`}
                ref={item.seriesId === selectedSeriesId ? selectedRow : undefined}
              >
                <Disclosure
                  title={`${item.seriesName}${item.isArchived ? " (archived)" : ""}`}
                  description={`Reminders ${global.notifyReminderEmails && item.notifyReminderEmails ? "on" : "off"} · Publication emails ${global.notifyRoundPublishedEmails && item.notifyRoundPublishedEmails ? "on" : "off"}`}
                  defaultOpen={item.seriesId === selectedSeriesId}
                >
                  {controls}
                </Disclosure>
              </div>
            );
          })}
        </div>
      </section>
      {seriesId && (
        <footer className="email-preferences-footer">
          <a href="/settings#notifications-title">Manage email preferences across all series</a>
          <span className="muted">Changes save automatically.</span>
        </footer>
      )}
    </div>
  );
}
