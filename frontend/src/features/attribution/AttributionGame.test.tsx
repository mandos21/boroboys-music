import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "../../components/ui/ToastProvider";
import { AttributionGame } from "./AttributionGame";
import type { AttributionStatus } from "./types";
import type { components } from "../../api/schema";

type Submission = components["schemas"]["SubmissionResponse"];

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

const status: AttributionStatus = {
  enabled: true,
  published: true,
  revealed: false,
  revealAt: new Date(Date.now() + 3_600_000).toISOString(),
  game: null,
  roster: [
    { contributor: { id: "me", displayName: "Me", spotifyProfileImageUrl: null }, maxGuesses: 1 },
    {
      contributor: { id: "alice", displayName: "Alice", spotifyProfileImageUrl: null },
      maxGuesses: 1,
    },
    { contributor: { id: "bob", displayName: "Bob", spotifyProfileImageUrl: null }, maxGuesses: 1 },
  ],
  leaderboard: [],
};

const tracks: Submission[] = [
  {
    id: "s-mine",
    status: "accepted",
    note: null,
    createdAt: "2026-09-01T00:00:00Z",
    updatedAt: "2026-09-01T00:00:00Z",
    withdrawnAt: null,
    isMine: true,
    contributor: { id: "me", displayName: "Me", spotifyProfileImageUrl: null },
    track: {
      spotifyTrackId: "t-mine",
      name: "My Song",
      artist: "Me Artist",
      album: null,
      spotifyUri: null,
      artworkUrl: null,
      providerMetadata: {},
    },
  },
  {
    id: "s-a",
    status: "accepted",
    note: null,
    createdAt: "2026-09-01T00:00:00Z",
    updatedAt: "2026-09-01T00:00:00Z",
    withdrawnAt: null,
    isMine: false,
    contributor: null,
    track: {
      spotifyTrackId: "t-a",
      name: "Song A",
      artist: "Artist A",
      album: null,
      spotifyUri: null,
      artworkUrl: null,
      providerMetadata: {},
    },
  },
  {
    id: "s-b",
    status: "accepted",
    note: null,
    createdAt: "2026-09-01T00:00:00Z",
    updatedAt: "2026-09-01T00:00:00Z",
    withdrawnAt: null,
    isMine: false,
    contributor: null,
    track: {
      spotifyTrackId: "t-b",
      name: "Song B",
      artist: "Artist B",
      album: null,
      spotifyUri: null,
      artworkUrl: null,
      providerMetadata: {},
    },
  },
];

function renderGame(onRevealed: () => void = vi.fn()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <ToastProvider>
      <QueryClientProvider client={client}>
        <AttributionGame
          roundId="round-1"
          status={status}
          tracks={tracks}
          onRevealed={onRevealed}
        />
      </QueryClientProvider>
    </ToastProvider>,
  );
}

describe("AttributionGame", () => {
  it("shows the viewer's own track as automatically filled in, excluded from the guessable pool", async () => {
    renderGame();
    // Shown, but not as a draggable/tappable guess target - own tracks need
    // no guessing and don't count toward "N of M placed".
    expect(screen.getByText("My Song")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /My Song/ })).toBeNull();
    expect(screen.getByText("Song A")).toBeTruthy();
    expect(screen.getByText("Song B")).toBeTruthy();
    expect(
      (screen.getByRole("button", { name: /lock in my guesses/i }) as HTMLButtonElement).disabled,
    ).toBe(true);
  });

  it("assigns tracks by tapping a track then a name, and enforces each member's submission limit", async () => {
    const user = userEvent.setup();
    renderGame();

    await user.click(screen.getByRole("button", { name: /Song A/ }));
    await user.click(screen.getByRole("button", { name: /Alice/ }));
    expect(screen.getByText("1 of 1 placed")).toBeTruthy();

    // Alice already has her one allowed guess - a second track can't go to her.
    await user.click(screen.getByRole("button", { name: /Song B/ }));
    await user.click(screen.getByRole("button", { name: /Alice/ }));
    expect(await screen.findByText(/as many as they could have submitted/i)).toBeTruthy();
    expect(
      (screen.getByRole("button", { name: /lock in my guesses/i }) as HTMLButtonElement).disabled,
    ).toBe(true);

    await user.click(screen.getByRole("button", { name: /Bob/ }));
    expect(
      (screen.getByRole("button", { name: /lock in my guesses/i }) as HTMLButtonElement).disabled,
    ).toBe(false);
  });

  it("submits guesses with snake_case ids and shows the scored reveal", async () => {
    const user = userEvent.setup();
    const onRevealed = vi.fn();
    let requestBody: unknown;
    vi.stubGlobal(
      "fetch",
      vi.fn((input: string | URL | Request, init?: RequestInit) => {
        const url = String(input);
        if (url.endsWith("/rounds/round-1/attribution/guesses")) {
          requestBody = JSON.parse(String(init?.body));
          return Promise.resolve(
            new Response(
              JSON.stringify({
                correctCount: 1,
                totalCount: 2,
                results: [
                  {
                    submissionId: "s-a",
                    guessedContributorId: "alice",
                    actualContributorId: "alice",
                    isCorrect: true,
                  },
                  {
                    submissionId: "s-b",
                    guessedContributorId: "bob",
                    actualContributorId: "alice",
                    isCorrect: false,
                  },
                ],
              }),
              { status: 200 },
            ),
          );
        }
        return Promise.resolve(new Response(JSON.stringify({}), { status: 200 }));
      }),
    );

    renderGame(onRevealed);
    await user.click(screen.getByRole("button", { name: /Song A/ }));
    await user.click(screen.getByRole("button", { name: /Alice/ }));
    await user.click(screen.getByRole("button", { name: /Song B/ }));
    await user.click(screen.getByRole("button", { name: /Bob/ }));
    await user.click(screen.getByRole("button", { name: /lock in my guesses/i }));

    await waitFor(() => expect(screen.getByText("1 / 2")).toBeTruthy());
    expect(requestBody).toEqual({
      guesses: [
        { submission_id: "s-a", contributor_id: "alice" },
        { submission_id: "s-b", contributor_id: "bob" },
      ],
    });

    await user.click(screen.getByRole("button", { name: /see the full submissions/i }));
    expect(onRevealed).toHaveBeenCalled();
  });
});
