import { describe, expect, it } from "vitest";

import { guessWhoAwards, selectGuessWhoAwards, type GuessWhoAward } from "./guessWhoAwards";
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

function candidate(title: string, lane: number, strength: number, ids: string[]): GuessWhoAward {
  return {
    title,
    lane,
    strength,
    variant: title.toLowerCase(),
    detail: "",
    explanation: "",
    people: ids.map((id) => ({ id, displayName: id, profileImageUrl: null })),
  };
}

describe("award selection across all four cards", () => {
  it("counts every tied winner and favors a stronger variety of stories", () => {
    const candidates = [
      candidate("Stumped", 0, 0.2, ["Kuba"]),
      candidate("Well-Known", 1, 0.189, ["Matt", "Kay"]),
      candidate("Imposter", 2, 1 / 3, ["Kay"]),
      candidate("Doppelgängers", 2, 2 / 9, ["Kevin", "Steve"]),
      candidate("Unanimous", 3, 1, ["Kay"]),
      candidate("Plot Twist", 3, 0.75, ["Kay"]),
      candidate("Split Decision", 3, 0.75, ["Nick"]),
    ];
    const selected = selectGuessWhoAwards(candidates);
    expect(selected.map((award) => award.title)).toEqual([
      "Stumped",
      "Well-Known",
      "Doppelgängers",
      "Unanimous",
    ]);
    expect(selectGuessWhoAwards([...candidates].reverse())).toEqual(selected);
    candidates[1].people.reverse();
    expect(selectGuessWhoAwards(candidates).map((award) => award.title)).toEqual(
      selected.map((award) => award.title),
    );
  });

  it("allows strong repeated findings but never duplicates the same mistaken-identity story", () => {
    const selected = selectGuessWhoAwards([
      candidate("Detective", 0, 0.4, ["A"]),
      candidate("Well-Known", 1, 0.4, ["A"]),
      candidate("Imposter", 2, 0.9, ["A"]),
      candidate("Doppelgängers", 2, 0.2, ["B", "C"]),
      candidate("Plot Twist", 3, 1, ["A"]),
      candidate("Unanimous", 3, 1, ["A"]),
    ]);
    expect(selected.map((award) => award.title)).toEqual([
      "Detective",
      "Well-Known",
      "Imposter",
      "Unanimous",
    ]);
    expect(
      selectGuessWhoAwards([
        candidate("Imposter", 2, 0.5, ["A"]),
        candidate("Plot Twist", 3, 0.8, ["A"]),
      ]),
    ).toHaveLength(1);
  });

  it("does not fill empty slots or depend on input order to resolve equal scores", () => {
    expect(selectGuessWhoAwards([])).toEqual([]);
    const candidates = [candidate("Stumped", 0, 0.2, ["A"]), candidate("Detective", 0, 0.2, ["B"])];
    expect(selectGuessWhoAwards(candidates)).toEqual(
      selectGuessWhoAwards([...candidates].reverse()),
    );
  });
});

describe("award evidence", () => {
  it("shows numerator and denominator with accuracy", () => {
    expect(scores(1).find((award) => award.title === "Detective")?.explanation).toBe(
      "80% · 8/10 guesses correct",
    );
    expect(scores(1).find((award) => award.title === "Elusive")?.explanation).toBe(
      "20% · 2/10 guesses correct on their tracks",
    );
  });

  it("preserves different denominators for tied winners", () => {
    const entries = people.map((contributor) => ({
      contributor,
      yourCorrectCount: null,
      yourTotalCount: null,
      groupCorrectCount: 1,
      groupTotalCount: 2,
      songs: [],
    }));
    const awards = guessWhoAwards(entries, [
      { contributor: people[0], correctCount: 4, totalCount: 5 },
      { contributor: people[1], correctCount: 8, totalCount: 10 },
    ]);
    expect(awards.find((award) => award.title === "Detective")?.explanation).toBe(
      "80% guesses correct · A: 4/5; B: 8/10",
    );
  });

  it("keeps one-player awards available and makes their limited evidence explicit", () => {
    const entries = [
      {
        contributor: people[0],
        yourCorrectCount: null,
        yourTotalCount: null,
        groupCorrectCount: 1,
        groupTotalCount: 1,
        songs: [
          {
            submissionId: "song",
            track: {
              name: "A pick",
              artist: "Artist",
              album: null,
              artworkUrl: null,
              spotifyTrackId: "spotify",
              spotifyUri: null,
            },
            groupCorrectCount: 1,
            groupTotalCount: 1,
            guesses: [{ guesser: people[1], guessedContributor: people[0], isCorrect: true }],
          },
        ],
      },
    ];
    const awards = guessWhoAwards(entries, [
      { contributor: people[1], correctCount: 1, totalCount: 1 },
    ]);
    expect(awards.find((award) => award.title === "Unanimous")?.explanation).toBe(
      "100% · 1/1 guesses correct",
    );
    expect(awards.find((award) => award.title === "Unanimous")?.detail).toContain("so far");
  });
});
