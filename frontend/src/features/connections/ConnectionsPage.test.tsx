import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ConnectionsPage } from "./ConnectionsPage";
import { ToastProvider } from "../../components/ui/ToastProvider";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

function connection(id: string, provider: string, displayName: string) {
  return {
    id,
    provider,
    displayName,
    profileImageUrl: null,
    visibility: "round_members",
    isActive: true,
    disconnectedAt: null,
  };
}

function renderConnections(connections: unknown[], path = "/profile") {
  vi.stubGlobal(
    "fetch",
    vi.fn(() => Promise.resolve(new Response(JSON.stringify(connections), { status: 200 }))),
  );
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <ToastProvider>
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={[path]}>
          <ConnectionsPage />
        </MemoryRouter>
      </QueryClientProvider>
    </ToastProvider>,
  );
}

describe("ConnectionsPage", () => {
  it("lists every linked account for a provider so each can be disconnected", async () => {
    renderConnections([
      connection("spotify-1", "spotify", "Main account"),
      connection("spotify-2", "spotify", "Second account"),
    ]);

    expect(await screen.findByText("Main account")).toBeTruthy();
    expect(screen.getByText("Second account")).toBeTruthy();
    expect(screen.getByRole("button", { name: /Disconnect Main account/ })).toBeTruthy();
    expect(screen.getByRole("button", { name: /Disconnect Second account/ })).toBeTruthy();
  });

  it("explains a failed provider link instead of leaving the page silent", async () => {
    renderConnections([], "/profile?linkError=already-linked&provider=spotify");

    expect(
      await screen.findByRole("heading", { name: /We couldn’t connect Spotify/ }),
    ).toBeTruthy();
    expect(screen.getByText(/already linked to a different person/)).toBeTruthy();
  });
});
