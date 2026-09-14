import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";

import { AttributionLeaderboard } from "./AttributionLeaderboard";
import type { AttributionLeaderboardEntry } from "./types";

const entries: AttributionLeaderboardEntry[] = [
  {
    contributor: { id: "alice", displayName: "Alice", spotifyProfileImageUrl: null },
    correctCount: 4,
    totalCount: 4,
  },
  {
    contributor: { id: "bob", displayName: "Bob", spotifyProfileImageUrl: null },
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
});
