import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { RoundPage } from "./RoundPages";
import { ToastProvider } from "../../components/ui/ToastProvider";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

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

function stubRoundFetch(round: Record<string, unknown>) {
  const requests: { url: string; method: string; body: unknown }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      const body = init?.body ? JSON.parse(String(init.body)) : undefined;
      requests.push({ url, method, body });
      if (url.endsWith("/rounds/round-1/participation")) {
        round = { ...round, declinedFurtherSubmissions: body.declined_further_submissions };
        return Promise.resolve(
          new Response(
            JSON.stringify({ declinedFurtherSubmissions: round.declinedFurtherSubmissions }),
            { status: 200 },
          ),
        );
      }
      if (url.endsWith("/rounds/round-1")) {
        return Promise.resolve(new Response(JSON.stringify(round), { status: 200 }));
      }
      return Promise.resolve(new Response(JSON.stringify([]), { status: 200 }));
    }),
  );
  return requests;
}

const baseRound = {
  id: "round-1",
  title: "September picks",
  status: "open",
  opensAt: "2026-09-01T00:00:00Z",
  closesAt: "2026-09-30T00:00:00Z",
  publishAt: "2026-10-01T00:00:00Z",
  submissionLimit: 2,
  declinedFurtherSubmissions: false,
};

describe("RoundPage", () => {
  it("offers a clear submission action only while the round is open", async () => {
    stubRoundFetch(baseRound);

    renderRound();

    expect(await screen.findByRole("heading", { name: "September picks" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Choose a track" })).toHaveProperty(
      "href",
      expect.stringContaining("/rounds/round-1/submit"),
    );
    expect(await screen.findByRole("heading", { name: "Submissions" })).toBeTruthy();
  });

  it("lets a member declare they're done submitting, without losing their pick capacity", async () => {
    const requests = stubRoundFetch(baseRound);

    renderRound();

    expect(await screen.findByText("I'm not submitting any more this round")).toBeTruthy();
    const toggle = screen.getByRole("switch");
    expect(toggle.getAttribute("aria-checked")).toBe("false");

    toggle.click();

    await waitFor(() =>
      expect(requests.some((request) => request.url.endsWith("/participation"))).toBe(true),
    );
    const participationRequest = requests.find((request) => request.url.endsWith("/participation"));
    expect(participationRequest?.method).toBe("PATCH");
    expect(participationRequest?.body).toEqual({ declined_further_submissions: true });
    await waitFor(() =>
      expect(screen.getByText(/you won.t get deadline reminders for it/).textContent).toBeTruthy(),
    );
  });
});
