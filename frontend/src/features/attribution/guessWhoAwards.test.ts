import { describe, expect, it } from "vitest";

import { guessWhoAwards } from "./guessWhoAwards";
import type { AttributionLeaderboardEntry, AttributionSubmitterBreakdown } from "./types";

const people = ["A", "B", "C"].map((name) => ({
  id: name,
  displayName: name,
  profileImageUrl: null,
}));

function scores(scale: number) {
  const correct = [8, 2, 5];
  const entries: AttributionSubmitterBreakdown[] = people.map((person, index) => ({
    contributor: person,
    yourCorrectCount: null,
    yourTotalCount: null,
    groupCorrectCount: correct[index] * scale,
    groupTotalCount: 10 * scale,
    songs: [],
  }));
  const leaderboard: AttributionLeaderboardEntry[] = people.map((person, index) => ({
    contributor: person,
    correctCount: correct[index] * scale,
    totalCount: 10 * scale,
  }));
  return guessWhoAwards(entries, leaderboard);
}

describe("Guess Who awards", () => {
  it("qualifies by accuracy and round-relative margin regardless of turnout", () => {
    expect(new Set(scores(1).map((award) => award.title))).toEqual(
      new Set(["Detective", "Well-Known", "Stumped", "Elusive"]),
    );
    expect(scores(4).map((award) => award.title)).toEqual(scores(1).map((award) => award.title));
  });

  it("leaves slots empty when nobody stands out", () => {
    const entries: AttributionSubmitterBreakdown[] = people.map((person) => ({
      contributor: person,
      yourCorrectCount: null,
      yourTotalCount: null,
      groupCorrectCount: 1,
      groupTotalCount: 2,
      songs: [],
    }));
    expect(guessWhoAwards(entries, [])).toEqual([]);
  });
});
