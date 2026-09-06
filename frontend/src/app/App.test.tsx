import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
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
      vi.fn().mockResolvedValue(
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

  it("gives signed-in contributors an actionable round dashboard", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: string | URL | Request) => {
        const url = String(input);
        if (url.endsWith("/auth/session")) {
          return Promise.resolve(new Response(JSON.stringify({
            user: { id: "listener-1", email: "listener@example.test", displayName: "Lena", platformRole: "member" },
          }), { status: 200 }));
        }
        if (url.endsWith("/rounds")) {
          return Promise.resolve(new Response(JSON.stringify([{
            id: "round-1",
            title: "September picks",
            status: "open",
            closesAt: "2026-09-30T23:59:59Z",
            publishAt: "2026-10-01T12:00:00Z",
            submissionLimit: 2,
          }]), { status: 200 }));
        }
        return Promise.resolve(new Response(JSON.stringify({ detail: "not found" }), { status: 404 }));
      }),
    );

    renderApp("/");

    expect(await screen.findByRole("heading", { name: "Your rounds" })).toBeTruthy();
    expect(await screen.findByRole("link", { name: /Open round/i })).toHaveProperty(
      "href",
      expect.stringContaining("/rounds/round-1"),
    );
  });
});
