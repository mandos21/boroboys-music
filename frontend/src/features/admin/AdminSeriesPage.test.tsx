import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from "react-router";
import { afterEach, expect, it, vi } from "vitest";
import { ToastProvider } from "../../components/ui/ToastProvider";
import { AdminSeriesPage } from "./AdminSeriesPage";

afterEach(() => vi.unstubAllGlobals());
const series = {
  id: "series",
  name: "Monthly Music",
  slug: "monthly",
  timezone: "America/New_York",
  description: null,
  defaultPolicies: [],
  roundPlan: null,
  autoStartNextRound: false,
  isArchived: false,
  coverImageUrl: null,
  accentColor: null,
  defaultAttributionRevealDelaySeconds: null,
  groups: [],
  rounds: [
    {
      id: "open",
      seriesId: "series",
      title: "October",
      status: "open",
      timezone: "America/New_York",
      opensAt: "2026-10-01T00:00:00Z",
      closesAt: "2026-10-31T23:59:00Z",
      publishAt: "2026-11-01T23:59:00Z",
      submissionLimit: 3,
      policySnapshot: [],
    },
    {
      id: "past",
      seriesId: "series",
      title: "September",
      status: "published",
      timezone: "America/New_York",
      opensAt: "2026-09-01T00:00:00Z",
      closesAt: "2026-09-30T23:59:00Z",
      publishAt: "2026-10-01T23:59:00Z",
      submissionLimit: 3,
      policySnapshot: [],
    },
  ],
};
const notifications = {
  channels: {
    emailReady: true,
    mattermostReady: false,
    mattermostMode: "disabled",
    sharedMattermostReady: false,
  },
  rules: [],
  upcoming: [],
  history: [],
  timezone: series.timezone,
};
function Location() {
  const location = useLocation();
  const navigate = useNavigate();
  return (
    <>
      <output aria-label="Current URL">{location.search}</output>
      <button onClick={() => navigate(-1)}>Browser back</button>
    </>
  );
}
function setup(entry = "/admin/series/series") {
  const requests: { path: string; method: string; body?: Record<string, unknown> }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: string, init?: RequestInit) => {
      requests.push({
        path,
        method: init?.method ?? "GET",
        body: init?.body ? JSON.parse(String(init.body)) : undefined,
      });
      const result = path.endsWith("/notifications")
        ? notifications
        : path.endsWith("/preview")
          ? {
              ruleId: "preview",
              ruleName: "Reminder",
              roundId: "open",
              roundTitle: "October",
              channel: "mattermost",
              scheduledAt: "2026-10-30T23:59:00Z",
              message: "Preview October",
              audience: "Mattermost channel",
              channelReady: false,
            }
          : path.endsWith("/members") || path.endsWith("/connections")
            ? []
            : series;
      return new Response(JSON.stringify(result), { status: 200 });
    }),
  );
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <ToastProvider>
        <MemoryRouter initialEntries={[entry]}>
          <Location />
          <Routes>
            <Route path="/admin/series/:seriesId" element={<AdminSeriesPage />} />
          </Routes>
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  );
  return { requests, user: userEvent.setup() };
}

it("uses URL tabs, separates past rounds, and loads notification data on demand", async () => {
  const { requests, user } = setup();
  expect(await screen.findByRole("heading", { name: "Current and upcoming rounds" })).toBeTruthy();
  expect(screen.getByText("October")).toBeTruthy();
  expect(screen.queryByText("September")).toBeNull();
  expect(requests.some((request) => request.path.endsWith("/notifications"))).toBe(false);
  await user.click(screen.getByRole("link", { name: "History" }));
  expect(screen.getByRole("heading", { name: "Past rounds" })).toBeTruthy();
  expect(screen.getByLabelText("Current URL").textContent).toBe("?tab=history");
  await user.click(screen.getByRole("link", { name: "Notifications" }));
  expect(await screen.findByRole("heading", { name: "Notification rules" })).toBeTruthy();
  await user.click(screen.getByRole("button", { name: "Browser back" }));
  expect(screen.getByRole("heading", { name: "Past rounds" })).toBeTruthy();
});

it("preserves a notification draft across tabs and previews without sending", async () => {
  const { requests, user } = setup("/admin/series/series?tab=notifications");
  await user.click(await screen.findByRole("button", { name: "Add notification" }));
  await user.type(screen.getByLabelText("Rule name"), "Last call");
  await user.selectOptions(screen.getByLabelText("Unit"), "60");
  await user.clear(screen.getByLabelText("How long"));
  await user.type(screen.getByLabelText("How long"), "6");
  await user.click(screen.getByRole("link", { name: "Members" }));
  expect(await screen.findByRole("heading", { name: "Series members" })).toBeTruthy();
  await user.click(screen.getByRole("link", { name: "Notifications" }));
  expect((screen.getByLabelText("Rule name") as HTMLInputElement).value).toBe("Last call");
  await user.click(screen.getByRole("button", { name: "Preview message" }));
  expect(await screen.findByText("Preview October")).toBeTruthy();
  expect(
    requests.filter((request) => request.method === "POST").map((request) => request.path),
  ).toEqual(["/api/v1/admin/series/series/notifications/preview"]);
  await user.click(screen.getByRole("button", { name: "Save rule" }));
  await waitFor(() =>
    expect(requests.some((request) => request.path.endsWith("/rules"))).toBe(true),
  );
  expect(requests.find((request) => request.path.endsWith("/rules"))?.body).toMatchObject({
    name: "Last call",
    offset_minutes: -360,
    channel: "mattermost",
  });
});

it("redirects old Automation links to Rounds and groups defaults with series details", async () => {
  const { requests, user } = setup("/admin/series/series?tab=automation");
  const settings = await screen.findByRole("region", { name: "Round settings" });
  await waitFor(() => expect(screen.getByLabelText("Current URL").textContent).toBe("?tab=rounds"));
  expect(screen.queryByRole("link", { name: "Automation" })).toBeNull();
  expect(within(settings).getByRole("button", { name: "Edit series details" })).toBeTruthy();
  await user.click(within(settings).getByRole("button", { name: /Guess Who defaults/ }));
  await user.click(screen.getByRole("switch", { name: "Enable Guess Who for new rounds" }));
  await user.click(screen.getByRole("button", { name: "Save Guess Who defaults" }));
  await waitFor(() => expect(requests.some((request) => request.method === "PATCH")).toBe(true));
  expect(requests.find((request) => request.method === "PATCH")?.body).toEqual({
    default_attribution_reveal_delay_seconds: 3600,
  });
  await user.click(screen.getByRole("button", { name: "Edit series details" }));
  const dialog = screen.getByRole("dialog");
  expect(within(dialog).getByLabelText("Description")).toBeTruthy();
  expect(within(dialog).queryByText("Guess Who defaults")).toBeNull();
});

it("keeps settings and automation drafts when collapsing sections and changing tabs", async () => {
  const { user } = setup();
  const settings = await screen.findByRole("region", { name: "Round settings" });
  const rounds = screen.getByRole("region", { name: "Current and upcoming rounds" });
  await user.click(within(settings).getByRole("button", { name: /Guess Who defaults/ }));
  await user.click(
    within(settings).getByRole("switch", { name: "Enable Guess Who for new rounds" }),
  );
  const minutes = within(settings).getByLabelText("Minutes to keep names hidden after publishing");
  await user.clear(minutes);
  await user.type(minutes, "90");
  await user.click(within(rounds).getByRole("button", { name: /Round automation/ }));
  await user.selectOptions(within(rounds).getByLabelText("Timeline"), "rolling");
  await user.type(within(rounds).getByLabelText(/How many days/), "14");
  await user.click(within(rounds).getByRole("button", { name: /Round automation/ }));
  await user.click(screen.getByRole("link", { name: "Members" }));
  expect(screen.queryByRole("button", { name: "Edit series details" })).toBeNull();
  await user.click(screen.getByRole("link", { name: "Rounds" }));
  expect((within(settings).getByLabelText(/Minutes to keep names/) as HTMLInputElement).value).toBe(
    "90",
  );
  await user.click(within(rounds).getByRole("button", { name: /Round automation/ }));
  expect((within(rounds).getByLabelText(/How many days/) as HTMLInputElement).value).toBe("14");
});

it("validates automation duration and allows disabling it with an invalid unused limit", async () => {
  const { user, requests } = setup();
  await user.click(await screen.findByRole("button", { name: /Round automation/ }));
  await user.selectOptions(screen.getByLabelText("Timeline"), "rolling");
  await user.type(screen.getByLabelText(/How many days/), "366");
  await user.click(screen.getByRole("button", { name: "Save plan" }));
  expect(await screen.findByText("Use a whole number of days from 1 to 365.")).toBeTruthy();
  expect(requests.filter((r) => r.method === "PATCH")).toHaveLength(0);
  await user.type(screen.getByLabelText(/Tracks each contributor/), "-1");
  await user.selectOptions(screen.getByLabelText("Timeline"), "none");
  await user.click(screen.getByRole("button", { name: "Save plan" }));
  await waitFor(() =>
    expect(requests.find((r) => r.method === "PATCH")?.body).toEqual({
      auto_start_next_round: false,
      round_plan: null,
    }),
  );
});
