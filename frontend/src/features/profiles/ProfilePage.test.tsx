import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "../../components/ui/ToastProvider";
import { ProfilePage } from "./ProfilePage";

afterEach(() => vi.restoreAllMocks());

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
    genreSpread: [{ name: "dream pop", count: 2 }],
    activity: [{ month: "2026-09", label: "Sep 2026", count: 3 }],
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

function renderProfile(profileStatus = 200) {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: string | URL | Request) => {
      const url = String(input);
      const body = url.includes("/profiles/me") ? profile : [];
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
});
