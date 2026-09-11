import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "../../components/ui/ToastProvider";
import { SubmissionPage } from "./SubmissionPage";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

function renderSubmission() {
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
              submissionLimit: 1,
            }),
            { status: 200 },
          ),
        );
      }
      if (url.endsWith("/rounds/round-1/submissions")) {
        return Promise.resolve(
          new Response(JSON.stringify([{ id: "submission-1", isMine: true, status: "accepted" }]), {
            status: 200,
          }),
        );
      }
      return Promise.resolve(
        new Response(JSON.stringify({ detail: "not found" }), { status: 404 }),
      );
    }),
  );
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <ToastProvider>
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={["/rounds/round-1/submit"]}>
          <Routes>
            <Route path="/rounds/:roundId/submit" element={<SubmissionPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </ToastProvider>,
  );
}

describe("SubmissionPage", () => {
  it("does not present a disabled submission form after the contributor has filled their limit", async () => {
    renderSubmission();

    expect(await screen.findByText("You’re all set for this round")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Submit track" })).toBeNull();
    expect(screen.getByRole("link", { name: "View round" })).toHaveProperty(
      "href",
      expect.stringContaining("/rounds/round-1"),
    );
  });
});
