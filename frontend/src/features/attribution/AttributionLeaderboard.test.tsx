import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";

import { AttributionLeaderboard } from "./AttributionLeaderboard";
import type { AttributionLeaderboardEntry } from "./types";

const entries: AttributionLeaderboardEntry[] = [
  {
    contributor: { id: "alice", displayName: "Alice", profileImageUrl: null },
    correctCount: 4,
    totalCount: 4,
  },
  {
    contributor: { id: "bob", displayName: "Bob", profileImageUrl: null },
    correctCount: 2,
    totalCount: 4,
  },
];

describe("AttributionLeaderboard", () => {
  it("renders each entry's accuracy and links to their profile", () => {
    render(
      <MemoryRouter>
        <AttributionLeaderboard entries={entries} />
      </MemoryRouter>,
    );

    expect(screen.getByRole("heading", { name: "Leaderboard" })).toBeTruthy();
    expect(screen.getByText("100%")).toBeTruthy();
    expect(screen.getByText("50%")).toBeTruthy();
    expect(screen.getByRole("link", { name: /Alice/ })).toHaveProperty(
      "href",
      expect.stringContaining("/people/alice"),
    );
  });

  it("renders nothing when nobody has finished guessing yet", () => {
    const { container } = render(
      <MemoryRouter>
        <AttributionLeaderboard entries={[]} />
      </MemoryRouter>,
    );
    expect(container.textContent).toBe("");
  });

  it("uses the same rank for equal accuracy, even with different totals", () => {
    const tied = [
      entries[0],
      {
        ...entries[0],
        contributor: { id: "carol", displayName: "Carol", profileImageUrl: null },
        correctCount: 2,
        totalCount: 2,
      },
      entries[1],
    ];
    render(
      <MemoryRouter>
        <AttributionLeaderboard entries={tied} />
      </MemoryRouter>,
    );
    const ranks = Array.from(document.querySelectorAll(".attribution-leaderboard-rank"));
    expect(ranks.map((rank) => rank.textContent)).toEqual(["1", "1", "3"]);
  });

  it("does not call a game with no guesses 100% accurate", () => {
    render(
      <MemoryRouter>
        <AttributionLeaderboard entries={[{ ...entries[0], correctCount: 0, totalCount: 0 }]} />
      </MemoryRouter>,
    );
    expect(screen.queryByText("100%")).toBeNull();
    expect(screen.getByText("—")).toBeTruthy();
  });
});
