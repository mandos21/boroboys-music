import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "../../components/ui/ToastProvider";
import { ProfilePage } from "./ProfilePage";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

const profile = {
  id: "listener-1",
  displayName: "Mara Listener",
  spotifyProfileImageUrl: null,
  isMe: true,
  stats: {
    submissionCount: 3,
    uniqueTrackCount: 3,
    uniqueArtistCount: 2,
    uniqueAlbumCount: 2,
    uniqueGenreCount: 2,
    genreTaggedTrackCount: 3,
    diversityScore: 67,
    topArtists: [{ name: "The Testers", count: 2 }],
    genreSpread: [
      { name: "synth pop", count: 1, group: "pop" },
      { name: "dream pop", count: 2, group: "rock" },
    ],
    affinity: [
      {
        id: "user-2",
        displayName: "A Close Listener",
        spotifyProfileImageUrl: null,
        affinity: 72,
        sharedGenres: ["shoegaze", "midwest emo"],
        sharedRoundCount: 4,
      },
    ],
  },
  historyCount: 3,
  nextCursor: null,
  submissions: [
    {
      id: "submission-1",
      submittedAt: "2026-09-01T00:00:00Z",
      note: "A favorite",
      track: {
        spotifyTrackId: "track-1",
        name: "First pick",
        artist: "The Testers",
        album: "A record",
        spotifyUri: "spotify:track:track-1",
        artworkUrl: null,
        providerMetadata: {},
      },
      seriesId: "series-1",
      seriesName: "A series",
      roundId: "round-1",
      roundTitle: "September picks",
    },
  ],
};

function renderProfile(profileStatus = 200, profileData = profile) {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: string | URL | Request) => {
      const url = String(input);
      const body = url.includes("/profiles/me") ? profileData : [];
      return Promise.resolve(
        new Response(JSON.stringify(body), {
          status: url.includes("/profiles/") ? profileStatus : 200,
        }),
      );
    }),
  );
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <ToastProvider>
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={["/profile"]}>
          <Routes>
            <Route path="/profile" element={<ProfilePage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </ToastProvider>,
  );
}

describe("ProfilePage", () => {
  it("turns a listener's history into readable stats, insight panels, and track links", async () => {
    renderProfile();

    expect(await screen.findByRole("heading", { name: "Your record, so far." })).toBeTruthy();
    expect(screen.getByText("Tracks shared")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Most shared artists" })).toBeTruthy();
    expect(screen.getByText("dream pop")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "rock: 2 tags" }));
    expect(document.querySelector(".profile-genre-pills .genre-token")?.textContent).toContain(
      "dream pop",
    );
    expect(screen.getByText("dream pop").className).toContain("is-highlighted");
    expect(screen.getByText("synth pop").className).toContain("is-muted");
    expect(document.querySelector(".profile-genre-pills .genre-token")).toBeTruthy();
    expect(screen.getByText("First pick")).toBeTruthy();
    expect(screen.getByRole("link", { name: "September picks" })).toHaveProperty(
      "href",
      expect.stringContaining("/rounds/round-1"),
    );
  });

  it("keeps connected services available if profile analytics fail", async () => {
    renderProfile(500);

    expect(
      await screen.findByRole("heading", { name: "Listening profile unavailable" }),
    ).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Connected services" })).toBeTruthy();
  });

  it("keeps a long fingerprint to five rows until the disclosure is opened", async () => {
    const longProfile = {
      ...profile,
      stats: {
        ...profile.stats,
        genreSpread: Array.from({ length: 6 }, (_, index) => ({
          name: `genre ${index + 1}`,
          count: 1,
          group: "rock",
        })),
      },
    };
    vi.spyOn(HTMLElement.prototype, "offsetTop", "get").mockImplementation(function (
      this: HTMLElement,
    ) {
      if (!this.classList.contains("genre-token")) return 0;
      return [...document.querySelectorAll(".genre-token")].indexOf(this) * 24;
    });
    vi.spyOn(HTMLElement.prototype, "offsetHeight", "get").mockImplementation(function (
      this: HTMLElement,
    ) {
      return this.classList.contains("genre-token") ? 20 : 0;
    });
    renderProfile(200, longProfile);

    const disclosure = await screen.findByRole("button", { name: "All 6 genres" });
    expect(disclosure.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(disclosure);
    expect(disclosure.textContent).toContain("Fewer genres");
    expect(disclosure.getAttribute("aria-expanded")).toBe("true");
  });
});
