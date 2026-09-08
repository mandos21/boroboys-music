import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SeriesPage } from "./RoundPages";
import { ToastProvider } from "../../components/ui/ToastProvider";

afterEach(() => vi.restoreAllMocks());

const openRound = {
  id: "round-open",
  title: "September picks",
  status: "open",
  opensAt: "2026-09-01T00:00:00Z",
  closesAt: "2026-09-30T00:00:00Z",
  publishAt: "2026-10-01T00:00:00Z",
  prompt: null,
  artworkUrls: [],
};

const publishedRound = {
  id: "round-published",
  title: "August picks",
  status: "published",
  opensAt: "2026-08-01T00:00:00Z",
  closesAt: "2026-08-31T00:00:00Z",
  publishAt: "2026-09-01T00:00:00Z",
  prompt: null,
  artworkUrls: [],
};

function renderSeries(rounds: unknown[]) {
  vi.stubGlobal(
    "fetch",
    vi.fn(() =>
      Promise.resolve(
        new Response(
          JSON.stringify({
            id: "series-1",
            name: "Boro Boys Monthly",
            description: null,
            timezone: "UTC",
            coverImageUrl: null,
            accentColor: null,
            fallbackArtworkUrl: null,
            isAdmin: false,
            stats: { roundCount: rounds.length, songCount: 0, artistCount: 0, contributors: [] },
            rounds,
          }),
          { status: 200 },
        ),
      ),
    ),
  );
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <ToastProvider>
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={["/series/series-1"]}>
          <Routes>
            <Route path="/series/:seriesId" element={<SeriesPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </ToastProvider>,
  );
}

describe("SeriesPage", () => {
  it("leads with the open round rather than the most recent release", async () => {
    // The API sorts an open round first; the page must not reorder past it.
    renderSeries([openRound, publishedRound]);

    const featured = await screen.findByRole("link", { name: /Current round/ });
    expect(within(featured).getByRole("heading", { name: "September picks" })).toBeTruthy();
  });

  it("keeps an unpublished round out of the release archive", async () => {
    renderSeries([openRound, publishedRound]);

    await screen.findByRole("link", { name: /Current round/ });
    // "Published <date>" belongs only to rounds that actually have one.
    expect(screen.queryByText(/September picks/)).toBeTruthy();
    const archive = screen.getAllByText(/Published/);
    for (const entry of archive) {
      expect(entry.textContent).not.toContain("September picks");
    }
  });

  it("features the latest release when nothing is open", async () => {
    renderSeries([publishedRound]);

    const featured = await screen.findByRole("link", { name: /Latest release/ });
    expect(within(featured).getByRole("heading", { name: "August picks" })).toBeTruthy();
  });
});
