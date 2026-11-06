import { describe, expect, it } from "vitest";
import { roundAction, sortHomeSeries, type DashboardRound, type HomeSeries } from "./homeState";

const now = Date.parse("2026-09-10T12:00:00Z");
const round: DashboardRound = {
  id: "r1",
  title: "September",
  status: "open",
  opensAt: "2026-09-01T00:00:00Z",
  closesAt: "2026-10-01T00:00:00Z",
  publishAt: "2026-10-02T00:00:00Z",
  isMember: true,
  yourSubmissionCount: 0,
  submissionLimit: 3,
  declinedFurtherSubmissions: false,
  artworkUrls: [],
  spotifyPlaylistUrl: null,
  publishedAt: null,
  contributorCount: 5,
  submittedCount: 2,
  prompt: null,
};

describe("personal home actions", () => {
  it.each([
    [{}, "Choose a track", 0],
    [{ yourSubmissionCount: 1 }, "Add another track", 1],
    [{ yourSubmissionCount: 3 }, "View your picks", 2],
    [{ yourSubmissionCount: 4 }, "View your picks", 2],
    [{ yourSubmissionCount: 1, declinedFurtherSubmissions: true }, "View your picks", 2],
    [{ declinedFurtherSubmissions: true }, "View round", 2],
    [{ submissionLimit: 0 }, "View round", 2],
    [{ yourSubmissionCount: 3, submissionLimit: 5 }, "Add another track", 1],
    [{ isMember: false }, "View round", 3],
    [{ status: "closed" }, "View round", 4],
    [{ status: "draft" }, "View round", 5],
    [{ status: "cancelled" }, "View round", 5],
    [{ status: "failed" }, "View round", 4],
    [{ status: "unpublishing" }, "View round", 4],
    [{ closesAt: "2026-09-09T00:00:00Z" }, "View round", 4],
  ] as const)("uses participation for %j", (change, label, priority) => {
    expect(roundAction({ ...round, ...change }, now)).toMatchObject({ label, priority });
  });
  it("never claims an empty closed round has your picks", () => {
    expect(roundAction({ ...round, status: "closed" }, now).message).not.toContain(
      "Your picks are in",
    );
  });
  it("sorts unanswered rounds before partial and complete rounds, with nearest deadline first", () => {
    const series = (id: string, count: number, closesAt = round.closesAt) =>
      ({
        id,
        name: id,
        featuredRound: { ...round, yourSubmissionCount: count, closesAt },
      }) as HomeSeries;
    const items = [
      series("done", 3),
      series("partial", 1),
      series("later", 0),
      series("first", 0, "2026-09-15T00:00:00Z"),
    ];
    expect(sortHomeSeries(items, now).map((item) => item.id)).toEqual([
      "first",
      "later",
      "partial",
      "done",
    ]);
    expect(items[0].id).toBe("done");
  });
});
