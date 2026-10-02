import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AttributionMatrix } from "./AttributionMatrix";
import type { AttributionSubmitterBreakdown } from "./types";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

function contributor(id: string, displayName: string) {
  return { id, displayName, profileImageUrl: null };
}

function track(name: string) {
  return {
    spotifyTrackId: `t-${name}`,
    name,
    artist: "Someone",
    album: null,
    spotifyUri: null,
    artworkUrl: null,
    providerMetadata: {},
  };
}

const alice = contributor("alice", "Alice");
const bob = contributor("bob", "Bob");
const carol = contributor("carol", "Carol");

// Alice's song: both Bob and Carol correctly guess Alice.
// Bob's song: Alice and Carol both (wrongly) guess Carol.
// Carol's song: Alice (wrongly) guesses Bob.
const breakdown: AttributionSubmitterBreakdown[] = [
  {
    contributor: alice,
    yourCorrectCount: null,
    yourTotalCount: null,
    groupCorrectCount: 2,
    groupTotalCount: 2,
    songs: [
      {
        submissionId: "s-alice",
        track: track("Alice Song"),
        groupCorrectCount: 2,
        groupTotalCount: 2,
        guesses: [
          { guesser: bob, guessedContributor: alice, isCorrect: true },
          { guesser: carol, guessedContributor: alice, isCorrect: true },
        ],
      },
    ],
  },
  {
    contributor: bob,
    yourCorrectCount: null,
    yourTotalCount: null,
    groupCorrectCount: 0,
    groupTotalCount: 2,
    songs: [
      {
        submissionId: "s-bob",
        track: track("Bob Song"),
        groupCorrectCount: 0,
        groupTotalCount: 2,
        guesses: [
          { guesser: alice, guessedContributor: carol, isCorrect: false },
          { guesser: carol, guessedContributor: carol, isCorrect: false },
        ],
      },
    ],
  },
  {
    contributor: carol,
    yourCorrectCount: null,
    yourTotalCount: null,
    groupCorrectCount: 0,
    groupTotalCount: 1,
    songs: [
      {
        submissionId: "s-carol",
        track: track("Carol Song"),
        groupCorrectCount: 0,
        groupTotalCount: 1,
        guesses: [{ guesser: alice, guessedContributor: bob, isCorrect: false }],
      },
    ],
  },
];

function renderMatrix(enabled = true) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  vi.stubGlobal(
    "fetch",
    vi.fn((input: string | URL | Request) => {
      const url = String(input);
      if (url.endsWith("/rounds/round-1/attribution/breakdown")) {
        return Promise.resolve(new Response(JSON.stringify(breakdown), { status: 200 }));
      }
      return Promise.resolve(new Response(JSON.stringify({}), { status: 200 }));
    }),
  );
  return render(
    <QueryClientProvider client={client}>
      <AttributionMatrix roundId="round-1" enabled={enabled} />
    </QueryClientProvider>,
  );
}

describe("AttributionMatrix", () => {
  it("renders nothing and fetches nothing when not yet revealed", () => {
    renderMatrix(false);
    expect(fetch).not.toHaveBeenCalled();
    expect(screen.queryByText("Who got mixed up with who")).toBeNull();
  });

  it("aggregates every correct guess for a person into one diagonal cell", async () => {
    renderMatrix();
    const cell = await screen.findByRole("button", {
      name: "Bob and Carol correctly guessed Alice",
    });
    expect(cell.textContent).toBe("2");
  });

  it("aggregates multiple wrong guesses for the same mistaken pair into one cell", async () => {
    renderMatrix();
    const cell = await screen.findByRole("button", {
      name: "Alice and Carol guessed Bob's songs were Carol's",
    });
    expect(cell.textContent).toBe("2");
  });

  it("keeps a single wrong guess as its own cell", async () => {
    renderMatrix();
    const cell = await screen.findByRole("button", {
      name: "Alice guessed Carol's songs were Bob's",
    });
    expect(cell.textContent).toBe("1");
  });

  it("renders no button for a pair nobody guessed", async () => {
    renderMatrix();
    await screen.findByRole("button", { name: "Bob and Carol correctly guessed Alice" });
    // Alice was never guessed to be Bob, and Bob was never guessed to be Alice.
    expect(screen.queryByRole("button", { name: /Alice's songs were Bob's$/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /Bob's songs were Alice's$/ })).toBeNull();
  });

  it("lists everyone in the legend", async () => {
    renderMatrix();
    await screen.findByRole("button", { name: "Bob and Carol correctly guessed Alice" });
    const legend = document.querySelector(".attribution-matrix-legend");
    expect(legend).not.toBeNull();
    expect(legend?.textContent).toContain("Alice");
    expect(legend?.textContent).toContain("Bob");
    expect(legend?.textContent).toContain("Carol");
  });
});
