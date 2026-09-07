import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { RoundPage } from "./RoundPages";
import { ToastProvider } from "../../components/ui/ToastProvider";

afterEach(() => vi.restoreAllMocks());

function renderRound() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <ToastProvider>
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={["/rounds/round-1"]}>
          <Routes>
            <Route path="/rounds/:roundId" element={<RoundPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </ToastProvider>,
  );
}

describe("RoundPage", () => {
  it("offers a clear submission action only while the round is open", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: string | URL | Request) => {
        const url = String(input);
        if (url.endsWith("/rounds/round-1")) {
          return Promise.resolve(
            new Response(
              JSON.stringify({
                id: "round-1",
                title: "September picks",
                status: "open",
                opensAt: "2026-09-01T00:00:00Z",
                closesAt: "2026-09-30T00:00:00Z",
                publishAt: "2026-10-01T00:00:00Z",
                submissionLimit: 2,
              }),
              { status: 200 },
            ),
          );
        }
        return Promise.resolve(
          new Response(JSON.stringify([]), { status: 200 }),
        );
      }),
    );

    renderRound();

    expect(
      await screen.findByRole("heading", { name: "September picks" }),
    ).toBeTruthy();
    expect(screen.getByRole("link", { name: "Choose a track" })).toHaveProperty(
      "href",
      expect.stringContaining("/rounds/round-1/submit"),
    );
    expect(
      await screen.findByRole("heading", { name: "Submissions" }),
    ).toBeTruthy();
  });
});
