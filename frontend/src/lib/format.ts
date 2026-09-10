export function formatDate(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

export function formatDateOnly(value: string): string {
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(new Date(value));
}

export function formatDeadline(value: string, action = "Closes"): string {
  const milliseconds = new Date(value).getTime() - Date.now();
  const days = Math.ceil(milliseconds / 86_400_000);
  if (days <= -2) return `${action} closed ${Math.abs(days)} days ago`;
  if (days === -1) return `${action} closed yesterday`;
  if (days === 0) return `${action} today`;
  if (days === 1) return `${action} tomorrow`;
  return `${action} in ${days} days`;
}
