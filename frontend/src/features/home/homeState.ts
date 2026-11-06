import type { components } from "../../api/schema";

export type DashboardRound = components["schemas"]["DashboardRoundResponse"];
export type HomeSeries = components["schemas"]["SeriesListResponse"];

export function roundAction(round: DashboardRound, now: number) {
  const base = `/rounds/${round.id}`;
  const view = { label: "View round", to: base, priority: 4 };
  if (round.status === "published")
    return { ...view, message: "The playlist is ready.", phase: "Released" };
  if (round.status === "cancelled")
    return { ...view, priority: 5, message: "This round was cancelled.", phase: "Cancelled" };
  if (round.status === "draft")
    return { ...view, priority: 5, message: "This round is still being planned.", phase: "Draft" };
  if (round.status === "failed")
    return { ...view, message: "The playlist hasn’t been released yet.", phase: "Release delayed" };
  if (round.status === "unpublishing")
    return { ...view, message: "The playlist is being updated.", phase: "Being updated" };
  if (round.status === "scheduled" || now < Date.parse(round.opensAt))
    return { ...view, message: "A new round is on its way.", phase: "Up next" };
  if (round.status !== "open" || now >= Date.parse(round.closesAt))
    return {
      ...view,
      message:
        round.yourSubmissionCount > 0
          ? "Your picks are in. Waiting for the playlist."
          : "Submissions are closed. The playlist is on its way.",
      phase: "Coming soon",
    };
  if (!round.isMember)
    return { ...view, message: "The group is sharing its picks.", phase: "Open now", priority: 3 };
  const count = round.yourSubmissionCount;
  const remaining = Math.max(0, round.submissionLimit - count);
  if (round.declinedFurtherSubmissions || remaining === 0)
    return {
      label: count ? "View your picks" : "View round",
      to: count ? `${base}#round-submissions` : base,
      priority: 2,
      message: count
        ? `Your ${count === 1 ? "pick is" : "picks are"} in. You’re all set.`
        : "You’re all set for this round.",
      phase: "Open now",
    };
  return {
    label: count ? "Add another track" : "Choose a track",
    to: `${base}/submit`,
    priority: count ? 1 : 0,
    message: count
      ? `You’ve shared ${count} of ${round.submissionLimit} tracks. Room for ${remaining} more.`
      : `Share up to ${round.submissionLimit} ${round.submissionLimit === 1 ? "track" : "tracks"} with the group.`,
    phase: "Open now",
  };
}

export function sortHomeSeries(items: HomeSeries[], now: number) {
  return [...items].sort((a, b) => {
    const ar = a.featuredRound;
    const br = b.featuredRound;
    const priority =
      (ar ? roundAction(ar, now).priority : 5) - (br ? roundAction(br, now).priority : 5);
    return (
      priority ||
      (ar && br ? Date.parse(ar.closesAt) - Date.parse(br.closesAt) : 0) ||
      a.name.localeCompare(b.name)
    );
  });
}
