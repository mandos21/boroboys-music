import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

function renderApp(path: string) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("application recovery screens", () => {
  it("explains an unavailable OIDC provider without exposing an API error", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          new Response(JSON.stringify({ detail: "not signed in" }), { status: 401 }),
        ),
    );

    renderApp("/auth/error?reason=oidc-unavailable");

    expect(await screen.findByRole("heading", { name: "We couldn’t sign you in" })).toBeTruthy();
    expect(screen.getByText(/identity provider is unavailable/i)).toBeTruthy();
    expect(screen.getByRole("link", { name: "Try signing in again" })).toHaveProperty(
      "href",
      expect.stringContaining("/api/v1/auth/login"),
    );
  });

  it("organizes a signed-in contributor's home around series", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: string | URL | Request) => {
        const url = String(input);
        if (url.endsWith("/auth/session")) {
          return Promise.resolve(
            new Response(
              JSON.stringify({
                user: {
                  id: "listener-1",
                  email: "listener@example.test",
                  displayName: "Lena",
                  platformRole: "member",
                },
              }),
              { status: 200 },
            ),
          );
        }
        if (url.endsWith("/series")) {
          return Promise.resolve(
            new Response(
              JSON.stringify([
                {
                  id: "series-1",
                  name: "Monthly picks",
                  description: "A monthly listening ritual.",
                  timezone: "UTC",
                  isAdmin: false,
                  featuredRound: {
                    id: "round-1",
                    title: "September picks",
                    status: "open",
                    opensAt: "2026-09-01T00:00:00Z",
                    closesAt: "2026-09-30T23:59:59Z",
                    publishAt: "2026-10-01T12:00:00Z",
                    submittedCount: 2,
                    contributorCount: 5,
                  },
                },
              ]),
              { status: 200 },
            ),
          );
        }
        return Promise.resolve(
          new Response(JSON.stringify({ detail: "not found" }), { status: 404 }),
        );
      }),
    );

    renderApp("/");

    expect(await screen.findByRole("heading", { name: "Monthly picks" })).toBeTruthy();
    expect(await screen.findByRole("link", { name: "Open Monthly picks" })).toHaveProperty(
      "href",
      expect.stringContaining("/series/series-1"),
    );
    expect(screen.getByRole("link", { name: /September picks/i })).toHaveProperty(
      "href",
      expect.stringContaining("/rounds/round-1"),
    );
  });
});

describe("invite acceptance", () => {
  it("accepts the invite exactly once and then moves to the series", async () => {
    const requests: { url: string; method: string }[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn((input: string | URL | Request, init?: RequestInit) => {
        const url = String(input);
        requests.push({ url, method: init?.method ?? "GET" });
        if (url.endsWith("/auth/session")) {
          return Promise.resolve(
            new Response(
              JSON.stringify({
                user: { id: "u1", email: null, displayName: "Mara", platformRole: "member" },
                expiresAt: "2026-12-01T00:00:00Z",
                csrfCookieName: "music_rounds_session_csrf",
              }),
              { status: 200 },
            ),
          );
        }
        if (url.endsWith("/series/invites/token-1/accept")) {
          return Promise.resolve(
            new Response(JSON.stringify({ seriesId: "series-9", role: "contributor" }), {
              status: 200,
            }),
          );
        }
        // The series page is not under test; make it land on its error state.
        return Promise.resolve(new Response(JSON.stringify({ detail: "nope" }), { status: 403 }));
      }),
    );

    renderApp("/invites/token-1");

    expect(await screen.findByRole("heading", { name: "Series unavailable" })).toBeTruthy();
    const accepts = requests.filter((request) => request.url.endsWith("/accept"));
    expect(accepts).toEqual([{ url: "/api/v1/series/invites/token-1/accept", method: "POST" }]);
  });
});
