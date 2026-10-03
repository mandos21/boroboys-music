import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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
    { contributor: { id: "me", displayName: "Me", profileImageUrl: null }, maxGuesses: 1 },
    {
      contributor: { id: "alice", displayName: "Alice", profileImageUrl: null },
      maxGuesses: 1,
    },
    { contributor: { id: "bob", displayName: "Bob", profileImageUrl: null }, maxGuesses: 1 },
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
    contributor: { id: "me", displayName: "Me", profileImageUrl: null },
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
          viewerId="me"
          onRevealed={onRevealed}
        />
      </QueryClientProvider>
    </ToastProvider>,
  );
}

function dragTrack(track: Element, target: Element) {
  const data = new Map<string, string>();
  const dataTransfer = {
    setData: (type: string, value: string) => data.set(type, value),
    getData: (type: string) => data.get(type) ?? "",
    effectAllowed: "none",
  };
  fireEvent.dragStart(track, { dataTransfer });
  fireEvent.dragOver(target, { dataTransfer });
  fireEvent.drop(target, { dataTransfer });
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

  it("never offers the viewer's own name as a roster bin to drag tracks onto", async () => {
    renderGame();
    expect(screen.queryByRole("button", { name: /^Me\b/ })).toBeNull();
    expect(screen.getByRole("button", { name: /Alice/ })).toBeTruthy();
    expect(screen.getByRole("button", { name: /Bob/ })).toBeTruthy();
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

  it("drags an assigned track directly to another person and back to the tray", async () => {
    const user = userEvent.setup();
    renderGame();
    await user.click(screen.getByRole("button", { name: /Song A/ }));
    await user.click(screen.getByRole("button", { name: /Alice/ }));

    const aliceBin = screen
      .getByRole("button", { name: /Alice/ })
      .closest(".attribution-roster-bin");
    const bobBin = screen.getByRole("button", { name: /Bob/ }).closest(".attribution-roster-bin");
    const tray = screen.getByLabelText("Unassigned tracks");
    expect(aliceBin).not.toBeNull();
    expect(bobBin).not.toBeNull();

    dragTrack(screen.getByRole("button", { name: "Song AArtist A" }), bobBin!);
    expect(aliceBin?.textContent).toContain("0 of 1 placed");
    expect(bobBin?.textContent).toContain("Song A");
    expect(tray.textContent).not.toContain("Song A");

    dragTrack(screen.getByRole("button", { name: "Song AArtist A" }), tray);
    expect(bobBin?.textContent).toContain("0 of 1 placed");
    expect(tray.textContent).toContain("Song A");
  });

  it("keeps an assigned track in place when the destination is full", async () => {
    const user = userEvent.setup();
    renderGame();
    await user.click(screen.getByRole("button", { name: /Song A/ }));
    await user.click(screen.getByRole("button", { name: /Alice/ }));
    await user.click(screen.getByRole("button", { name: /Song B/ }));
    await user.click(screen.getByRole("button", { name: /Bob/ }));

    const aliceBin = screen
      .getByRole("button", { name: /Alice/ })
      .closest(".attribution-roster-bin");
    const bobBin = screen.getByRole("button", { name: /Bob/ }).closest(".attribution-roster-bin");
    dragTrack(screen.getByRole("button", { name: "Song AArtist A" }), bobBin!);
    expect(aliceBin?.textContent).toContain("Song A");
    expect(bobBin?.textContent).toContain("Song B");
    expect(await screen.findByText(/as many as they could have submitted/i)).toBeTruthy();
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
