import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AttributionLeaderboard } from "./AttributionLeaderboard";
import type { AttributionLeaderboardEntry } from "./types";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

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

function renderLeaderboard(entryList: AttributionLeaderboardEntry[]) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={client}>
        <AttributionLeaderboard roundId="round-1" entries={entryList} />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("AttributionLeaderboard", () => {
  it("renders each entry's accuracy and links to their profile", () => {
    renderLeaderboard(entries);

    expect(screen.getByRole("heading", { name: "Leaderboard" })).toBeTruthy();
    expect(screen.getByText("100%")).toBeTruthy();
    expect(screen.getByText("50%")).toBeTruthy();
    expect(screen.getByRole("link", { name: /Alice/ })).toHaveProperty(
      "href",
      expect.stringContaining("/people/alice"),
    );
  });

  it("renders nothing when nobody has finished guessing yet", () => {
    const { container } = renderLeaderboard([]);
    expect(container.textContent).toBe("");
  });

  it("opens a player's detailed answers from their row", async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      "fetch",
      vi.fn((input: string | URL | Request) => {
        const url = String(input);
        if (url.endsWith("/rounds/round-1/attribution/games/alice")) {
          return Promise.resolve(
            new Response(
              JSON.stringify({
                contributor: { id: "alice", displayName: "Alice", spotifyProfileImageUrl: null },
                submittedAt: "2026-09-14T12:00:00Z",
                correctCount: 4,
                totalCount: 4,
                items: [],
              }),
              { status: 200 },
            ),
          );
        }
        return Promise.resolve(new Response(JSON.stringify({}), { status: 200 }));
      }),
    );

    renderLeaderboard(entries);
    const aliceRow = screen.getByRole("link", { name: /Alice/ }).closest("li");
    if (!aliceRow) throw new Error("expected a row for Alice");
    await user.click(
      screen.getAllByRole("button", { name: /see answers/i })[
        [...aliceRow.parentElement!.children].indexOf(aliceRow)
      ],
    );

    expect(await screen.findByText("Alice's answers")).toBeTruthy();
  });
});
