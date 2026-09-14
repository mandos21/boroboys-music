import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SeriesPage } from "./RoundPages";
import { ToastProvider } from "../../components/ui/ToastProvider";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

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

function renderSeries(rounds: unknown[], insightStats?: Record<string, unknown>) {
  const insights = {
    genreTaggedTrackCount: 0,
    uniqueTrackCount: 0,
    genreSpread: [],
    contributors: [],
    ...insightStats,
  };
  const songCount =
    typeof insightStats?.uniqueTrackCount === "number"
      ? insightStats.uniqueTrackCount
      : Array.isArray(insightStats?.genreSpread)
        ? insightStats.genreSpread.length
        : 0;
  const history = {
    id: "series-1",
    name: "Boro Boys Monthly",
    description: null,
    timezone: "UTC",
    coverImageUrl: null,
    accentColor: null,
    fallbackArtworkUrl: null,
    isAdmin: false,
    stats: {
      roundCount: rounds.length,
      songCount,
      artistCount: 0,
      contributors: [],
    },
    rounds,
  };
  vi.stubGlobal(
    "fetch",
    vi.fn((input: string) =>
      Promise.resolve(
        new Response(JSON.stringify(input.endsWith("/insights") ? insights : history), {
          status: 200,
        }),
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
  it("shows the series fingerprint and each contributor's mix", async () => {
    renderSeries([publishedRound], {
      genreTaggedTrackCount: 8,
      uniqueTrackCount: 12,
      genreSpread: [
        { name: "midwest emo", count: 6, group: "punk" },
        { name: "shoegaze", count: 3, group: "alternative" },
      ],
      contributors: [
        {
          id: "user-1",
          displayName: "A Listener",
          spotifyProfileImageUrl: null,
          trackCount: 7,
          genres: [
            { name: "midwest emo", count: 5, group: "punk" },
            { name: "shoegaze", count: 2, group: "alternative" },
          ],
        },
      ],
    });

    expect(await screen.findByText("What this series leans on")).toBeTruthy();
    expect(screen.getByText("8 of 12 tracks tagged")).toBeTruthy();
    expect(screen.getByText("midwest emo")).toBeTruthy();
    expect(screen.getByText("Who brings what")).toBeTruthy();
    expect(screen.getByRole("list", { name: "Genre colour key" }).textContent).toContain(
      "punkalternative",
    );
    // The mix is announced for screen readers rather than left to colour alone.
    expect(screen.getByText("punk 5, alternative 2")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "A Listener" }));
    expect(screen.getByText("midwest emo").className).toContain("is-highlighted");
    expect(screen.getByText("shoegaze").className).toContain("is-highlighted");
    expect(screen.getByText("A Listener · 2 unique tags")).toBeTruthy();
    expect(document.querySelector(".series-genre-cloud .genre-token")?.textContent).toContain(
      "midwest emo",
    );
  });

  it("expands the paired genre cards together when there is more detail", async () => {
    vi.spyOn(Element.prototype, "scrollHeight", "get").mockReturnValue(400);
    vi.spyOn(Element.prototype, "clientHeight", "get").mockReturnValue(200);
    renderSeries([publishedRound], {
      genreSpread: Array.from({ length: 13 }, (_, index) => ({
        name: `genre ${index + 1}`,
        count: index + 1,
        group: "rock",
      })),
    });

    const reveal = await screen.findByRole("button", { name: "More detail" });
    expect(reveal.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(reveal);
    expect(reveal.textContent).toContain("Less detail");
    expect(reveal.getAttribute("aria-expanded")).toBe("true");
    expect(document.querySelectorAll(".series-insight-panel.is-expanded")).toHaveLength(2);
    document.querySelectorAll<HTMLElement>(".series-insight-items").forEach((item) => {
      item.scrollTop = 100;
    });
    fireEvent.click(reveal);
    expect(reveal.textContent).toContain("More detail");
    expect(
      [...document.querySelectorAll<HTMLElement>(".series-insight-items")].every(
        (item) => item.scrollTop === 0,
      ),
    ).toBe(true);
  });

  it("sorts and highlights contributors from the genre key or a fingerprint tag", async () => {
    renderSeries([publishedRound], {
      genreSpread: [
        { name: "jazz", count: 3, group: "jazz" },
        { name: "midwest emo", count: 2, group: "punk" },
        { name: "shoegaze", count: 2, group: "alternative" },
      ],
      contributors: [
        {
          id: "user-low-variety",
          displayName: "Low variety",
          spotifyProfileImageUrl: null,
          trackCount: 3,
          genres: [{ name: "jazz", count: 3, group: "jazz" }],
        },
        {
          id: "user-high-variety",
          displayName: "High variety",
          spotifyProfileImageUrl: null,
          trackCount: 4,
          genres: [
            { name: "midwest emo", count: 2, group: "punk" },
            { name: "shoegaze", count: 2, group: "alternative" },
          ],
        },
      ],
    });

    await screen.findByText("Who brings what");
    expect(document.querySelector(".genre-mix-list li")?.textContent).toContain("High variety");

    fireEvent.click(screen.getByRole("button", { name: "punk" }));
    expect(screen.getByText("Who brings punk")).toBeTruthy();
    expect(document.querySelector(".genre-mix-list li")?.textContent).toContain("High variety");
    expect(document.querySelector(".series-genre-cloud .genre-token")?.textContent).toContain(
      "midwest emo",
    );
    expect(screen.getByRole("button", { name: "Low variety" }).closest("li")?.className).toContain(
      "is-muted",
    );

    fireEvent.click(screen.getByRole("button", { name: "punk: 2 tags" }));
    expect(screen.getByText("Click a name or genre to explore the group.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "punk: 2 tags" }));
    expect(screen.getByText("Who brings punk")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: /midwest emo/ }));
    expect(screen.getByText("Who brings midwest emo")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Low variety" }).closest("li")?.className).toContain(
      "is-muted",
    );
  });

  it("keeps every contributor's bar colors intact when selecting a person", async () => {
    renderSeries([publishedRound], {
      genreSpread: [
        { name: "jazz", count: 3, group: "jazz" },
        { name: "midwest emo", count: 2, group: "punk" },
      ],
      contributors: [
        {
          id: "user-low-variety",
          displayName: "Low variety",
          spotifyProfileImageUrl: null,
          trackCount: 3,
          genres: [{ name: "jazz", count: 3, group: "jazz" }],
        },
        {
          id: "user-high-variety",
          displayName: "High variety",
          spotifyProfileImageUrl: null,
          trackCount: 2,
          genres: [{ name: "midwest emo", count: 2, group: "punk" }],
        },
      ],
    });

    await screen.findByText("Who brings what");
    fireEvent.click(screen.getByRole("button", { name: "High variety" }));

    // The other contributor's whole row dims, the selected one stays focused.
    expect(screen.getByRole("button", { name: "Low variety" }).closest("li")?.className).toContain(
      "is-muted",
    );
    expect(
      screen.getByRole("button", { name: "High variety" }).closest("li")?.className,
    ).not.toContain("is-muted");

    // Colors inside every bar stay intact - selecting a person never grays
    // out individual genre segments, only whole rows.
    const segments = document.querySelectorAll<HTMLElement>(".genre-mix-bar i");
    expect(segments.length).toBeGreaterThan(0);
    segments.forEach((segment) => expect(segment.className).not.toContain("is-muted"));
  });
});
