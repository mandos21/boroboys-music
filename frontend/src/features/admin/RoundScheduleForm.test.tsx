import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { RoundScheduleForm } from "./RoundScheduleForm";
import { ToastProvider } from "../../components/ui/ToastProvider";
import type { Connection, SeriesDetail, User } from "./types";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

const series = {
  id: "series-1",
  name: "Boro Boys Monthly",
  slug: "boro-boys-monthly",
  description: null,
  timezone: "UTC",
  defaultPolicies: [],
  roundPlan: null,
  autoStartNextRound: false,
  isArchived: false,
  coverImageUrl: null,
  accentColor: null,
  groups: [],
  rounds: [],
} as unknown as SeriesDetail;

const members = [{ id: "user-1", displayName: "A Listener", email: null }] as User[];

function renderForm(accounts: Connection[] = []) {
  const fetchMock = vi.fn<(input: unknown, init?: RequestInit) => Promise<Response>>(() =>
    Promise.resolve(new Response(JSON.stringify({ id: "round-1" }), { status: 201 })),
  );
  vi.stubGlobal("fetch", fetchMock);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <ToastProvider>
      <QueryClientProvider client={client}>
        <RoundScheduleForm
          series={series}
          members={members}
          spotifyAccounts={accounts}
          onScheduled={() => {}}
        />
      </QueryClientProvider>
    </ToastProvider>,
  );
  return fetchMock;
}

describe("RoundScheduleForm", () => {
  it("refuses a window that closes before it opens", async () => {
    const fetchMock = renderForm();
    const user = userEvent.setup();

    await user.type(screen.getByLabelText(/^Title/), "September picks");
    await user.clear(screen.getByLabelText(/^Opens/));
    await user.type(screen.getByLabelText(/^Opens/), "2026-09-30T00:00");
    await user.type(screen.getByLabelText(/^Closes/), "2026-09-01T00:00");
    await user.type(screen.getByLabelText(/^Publishes/), "2026-10-01T00:00");
    await user.click(screen.getByRole("button", { name: "Schedule round" }));

    expect(await screen.findByText("Closing must come after opening.")).toBeTruthy();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("submits a valid window, including the publishing account", async () => {
    const fetchMock = renderForm([
      { id: "acct-1", provider: "spotify", displayName: "Main", isActive: true } as Connection,
    ]);
    const user = userEvent.setup();

    await user.type(screen.getByLabelText(/^Title/), "September picks");
    await user.clear(screen.getByLabelText(/^Opens/));
    await user.type(screen.getByLabelText(/^Opens/), "2026-09-01T00:00");
    await user.type(screen.getByLabelText(/^Closes/), "2026-09-30T00:00");
    await user.type(screen.getByLabelText(/^Publishes/), "2026-10-01T00:00");
    await user.selectOptions(screen.getByLabelText(/Publishing account/), "acct-1");
    await user.click(screen.getByRole("button", { name: "Schedule round" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const body = JSON.parse(String(fetchMock.mock.calls[0][1]?.body));
    expect(body.title).toBe("September picks");
    expect(body.publisher_account_id).toBe("acct-1");
    expect(body.opens_at).toContain("2026-09-01");
    expect(body.contributor_user_ids).toEqual(["user-1"]);
  });
});
