import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, patch } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import type { components } from "../../api/schema";
import { StatePanel } from "../../components/ui/StatePanel";
import { useToast } from "../../components/ui/ToastProvider";
import { Switch } from "../../components/ui/switch";

type NotificationSettings = components["schemas"]["NotificationSettingsResponse"];
type NotificationSettingsUpdate = components["schemas"]["NotificationSettingsUpdate"];

// Responses are camelCase (the API's usual convention); this endpoint's PATCH
// body is snake_case, matching every other write endpoint in this app. Both
// keys come from the generated contract, so a renamed setting fails to
// compile here instead of at runtime.
const TOGGLES: {
  key: keyof NotificationSettings;
  requestKey: keyof NotificationSettingsUpdate;
  label: string;
  description: string;
}[] = [
  {
    key: "notifyReminderEmails",
    requestKey: "notify_reminder_emails",
    label: "Deadline reminders",
    description: "An email 48 and 24 hours before a round you're in closes for submissions.",
  },
  {
    key: "notifyRoundPublishedEmails",
    requestKey: "notify_round_published_emails",
    label: "Round published",
    description: "An email once a round you're in is published as a playlist.",
  },
];

export function NotificationSettingsPanel() {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const settings = useQuery({
    queryKey: queryKeys.notificationSettings(),
    queryFn: () => api<NotificationSettings>("/profiles/me/notification-settings"),
  });
  const update = useMutation({
    mutationFn: (change: NotificationSettingsUpdate) =>
      patch<NotificationSettings>("/profiles/me/notification-settings", change),
    // A refetch already in flight (window focus, remount) carries pre-PATCH
    // values and would overwrite the response written below; cancel it first.
    onMutate: () => queryClient.cancelQueries({ queryKey: queryKeys.notificationSettings() }),
    onSuccess: (data) => queryClient.setQueryData(queryKeys.notificationSettings(), data),
    onError: () =>
      showToast({
        title: "Couldn’t save notification setting",
        description: "Try again in a moment.",
        tone: "error",
      }),
  });

  if (settings.isLoading) {
    return (
      <StatePanel kind="loading" title="Checking your notification settings">
        Looking for your saved preferences.
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

  return (
    <div className="notification-settings">
      {TOGGLES.map(({ key, requestKey, label, description }) => (
        <label className="notification-toggle" key={key}>
          <span>
            <span className="notification-toggle-label">{label}</span>
            <span className="notification-toggle-description">{description}</span>
          </span>
          <Switch
            checked={settings.data[key]}
            onCheckedChange={(checked) => update.mutate({ [requestKey]: checked })}
            disabled={update.isPending}
          />
        </label>
      ))}
    </div>
  );
}
