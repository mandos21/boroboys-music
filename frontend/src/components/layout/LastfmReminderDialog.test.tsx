import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LastfmReminderDialog } from "./LastfmReminderDialog";

const DISMISSED_KEY = "music-rounds-lastfm-reminder-dismissed-at";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  window.localStorage.removeItem(DISMISSED_KEY);
});

function stubConnections(connections: object[]) {
  vi.stubGlobal(
    "fetch",
    vi.fn(() => Promise.resolve(new Response(JSON.stringify(connections), { status: 200 }))),
  );
}

function renderDialog(enabled = true) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <LastfmReminderDialog enabled={enabled} />
    </QueryClientProvider>,
  );
}

describe("LastfmReminderDialog", () => {
  it("prompts to link Last.fm when no active Last.fm connection exists", async () => {
    stubConnections([]);
    renderDialog();

    expect(await screen.findByText("Link your Last.fm?")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Connect Last.fm" })).toHaveProperty(
      "href",
      expect.stringContaining("/api/v1/connections/lastfm/login"),
    );
  });

  it("stays hidden once Last.fm is already linked", async () => {
    stubConnections([{ id: "c1", provider: "lastfm", displayName: "listener", isActive: true }]);
    renderDialog();

    await waitFor(() => expect(fetch).toHaveBeenCalled());
    await waitFor(() => expect(screen.queryByText("Link your Last.fm?")).toBeNull());
  });

  it("ignores a disconnected Last.fm account and still prompts", async () => {
    stubConnections([{ id: "c1", provider: "lastfm", displayName: "listener", isActive: false }]);
    renderDialog();

    expect(await screen.findByText("Link your Last.fm?")).toBeTruthy();
  });

  it("does nothing while disabled, such as on the connections page itself", () => {
    stubConnections([]);
    renderDialog(false);

    expect(fetch).not.toHaveBeenCalled();
    expect(screen.queryByText("Link your Last.fm?")).toBeNull();
  });

  it("snoozes for two weeks after being dismissed, instead of reappearing immediately", async () => {
    const user = userEvent.setup();
    stubConnections([]);
    renderDialog();

    await user.click(await screen.findByRole("button", { name: "Maybe later" }));
    expect(screen.queryByText("Link your Last.fm?")).toBeNull();
    expect(window.localStorage.getItem(DISMISSED_KEY)).not.toBeNull();
  });

  it("prompts again once a prior dismissal has aged past the cooldown", async () => {
    const twentyDaysAgo = new Date(Date.now() - 20 * 24 * 60 * 60 * 1000).toISOString();
    window.localStorage.setItem(DISMISSED_KEY, twentyDaysAgo);
    stubConnections([]);
    renderDialog();

    expect(await screen.findByText("Link your Last.fm?")).toBeTruthy();
  });
});
