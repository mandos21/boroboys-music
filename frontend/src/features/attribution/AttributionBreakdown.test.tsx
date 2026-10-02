import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";

import { AttributionBreakdown } from "./AttributionBreakdown";
import type { AttributionSubmitterBreakdown } from "./types";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

const breakdown: AttributionSubmitterBreakdown[] = [
  {
    contributor: { id: "me", displayName: "Me", profileImageUrl: null },
    yourCorrectCount: null,
    yourTotalCount: null,
    groupCorrectCount: 1,
    groupTotalCount: 1,
    songs: [
      {
        submissionId: "s-mine",
        track: {
          spotifyTrackId: "t-mine",
          name: "My Song",
          artist: "Me Artist",
          album: null,
          spotifyUri: null,
          artworkUrl: null,
          providerMetadata: {},
        },
        groupCorrectCount: 1,
        groupTotalCount: 1,
        guesses: [
          {
            guesser: { id: "alice", displayName: "Alice", profileImageUrl: null },
            guessedContributor: { id: "me", displayName: "Me", profileImageUrl: null },
            isCorrect: true,
          },
        ],
      },
    ],
  },
  {
    contributor: { id: "alice", displayName: "Alice", profileImageUrl: null },
    yourCorrectCount: 0,
    yourTotalCount: 1,
    groupCorrectCount: 0,
    groupTotalCount: 2,
    songs: [
      {
        submissionId: "s-alice",
        track: {
          spotifyTrackId: "t-alice",
          name: "Alice's Song",
          artist: "Alice Artist",
          album: null,
          spotifyUri: null,
          artworkUrl: null,
          providerMetadata: {},
        },
        groupCorrectCount: 0,
        groupTotalCount: 2,
        guesses: [
          {
            guesser: { id: "me", displayName: "Me", profileImageUrl: null },
            guessedContributor: { id: "bob", displayName: "Bob", profileImageUrl: null },
            isCorrect: false,
          },
          {
            guesser: { id: "carol", displayName: "Carol", profileImageUrl: null },
            guessedContributor: { id: "bob", displayName: "Bob", profileImageUrl: null },
            isCorrect: false,
          },
        ],
      },
    ],
  },
];

function renderBreakdown(enabled = true, entries = breakdown) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  vi.stubGlobal(
    "fetch",
    vi.fn((input: string | URL | Request) => {
      const url = String(input);
      if (url.endsWith("/rounds/round-1/attribution/breakdown")) {
        return Promise.resolve(new Response(JSON.stringify(entries), { status: 200 }));
      }
      return Promise.resolve(new Response(JSON.stringify({}), { status: 200 }));
    }),
  );
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <AttributionBreakdown roundId="round-1" viewerId="me" enabled={enabled} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("AttributionBreakdown", () => {
  it("renders nothing and fetches nothing when not yet revealed", () => {
    renderBreakdown(false);
    expect(fetch).not.toHaveBeenCalled();
    expect(screen.queryByText("By person")).toBeNull();
  });

  it("groups songs by submitter with group and personal accuracy", async () => {
    renderBreakdown();

    const people = within(await screen.findByRole("list", { name: "People and songs" }));
    expect(people.getByText("Me")).toBeTruthy();
    expect(people.getByText("Alice")).toBeTruthy();
    expect(people.getByText("Alice").closest("li")?.textContent).toContain("You: 0/1");
    // The viewer's own section never shows a personal "You:" stat.
    expect(people.getByText("Me").closest("li")?.textContent).not.toContain("You:");

    await screen.findByText("My Song");
  });

  it("expands the viewer's own submitter section by default, others collapsed", async () => {
    renderBreakdown();

    await screen.findByRole("list", { name: "People and songs" });
    expect(screen.getByText("My Song")).toBeTruthy();
    expect(screen.queryByText("Alice's Song")).toBeNull();
  });

  it("labels each guesser avatar with who they guessed", async () => {
    renderBreakdown();

    await screen.findByText("My Song");
    expect(screen.getByLabelText("Alice guessed correctly")).toBeTruthy();
  });

  it("groups multiple wrong guesses for the same mistaken target under one avatar with a count", async () => {
    const user = userEvent.setup();
    renderBreakdown();

    const people = within(await screen.findByRole("list", { name: "People and songs" }));
    await user.click(people.getByText("Alice"));
    const triggers = await screen.findAllByRole("button", {
      name: "Me and Carol guessed Bob",
    });
    expect(triggers).toHaveLength(1);
    expect(triggers[0].textContent).toContain("2");
    // Not rendered as two separate wrong avatars for the same target.
    expect(screen.queryByLabelText("Me guessed Bob")).toBeNull();
    expect(screen.queryByLabelText("Carol guessed Bob")).toBeNull();
  });

  it("shows tied confusion awards from incorrect guesses", async () => {
    renderBreakdown();
    const awards = within(await screen.findByLabelText("Guess Who awards"));
    expect(awards.getByText("Most confusing")).toBeTruthy();
    expect(awards.getByText("Most confused")).toBeTruthy();
    expect(awards.getByRole("link", { name: "Alice" })).toBeTruthy();
    expect(awards.getByRole("link", { name: "Me" })).toBeTruthy();
    expect(awards.getByRole("link", { name: "Carol" })).toBeTruthy();
  });

  it("omits confusion awards when every guess was correct", async () => {
    renderBreakdown(true, [breakdown[0]]);
    await screen.findByRole("list", { name: "People and songs" });
    expect(screen.queryByLabelText("Guess Who awards")).toBeNull();
  });
});
