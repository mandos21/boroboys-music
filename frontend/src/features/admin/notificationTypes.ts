import type { components } from "../../api/schema";

export type NotificationSettings = components["schemas"]["SeriesNotificationsResponse"];
export type NotificationRule = components["schemas"]["RuleResponse"];
export type NotificationPreview = components["schemas"]["UpcomingResponse"];
export const MILESTONES = {
  opens: "Round opens",
  closes: "Submissions close",
  scheduled_release: "Scheduled release",
  published: "Playlist published",
};
export function notificationTime(value: string | null, timezone: string) {
  return value
    ? new Intl.DateTimeFormat(undefined, {
        dateStyle: "medium",
        timeStyle: "short",
        timeZone: timezone,
      }).format(new Date(value))
    : "After successful publication";
}
export function ruleTiming(rule: Pick<NotificationRule, "offset_minutes" | "milestone">) {
  const minutes = Math.abs(rule.offset_minutes);
  const unit = minutes % 1440 === 0 ? "day" : minutes % 60 === 0 ? "hour" : "minute";
  const count = minutes / (unit === "day" ? 1440 : unit === "hour" ? 60 : 1);
  const amount = `${count} ${unit}${count === 1 ? "" : "s"}`;
  return `${minutes ? `${amount} ${rule.offset_minutes < 0 ? "before" : "after"} · ` : "At · "}${MILESTONES[rule.milestone]}`;
}
