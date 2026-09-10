import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "../../components/ui/ToastProvider";
import { NotificationSettingsPanel } from "./NotificationSettingsPanel";

afterEach(() => vi.restoreAllMocks());

function renderPanel() {
  const initial = { notifyReminderEmails: true, notifyRoundPublishedEmails: true };
  const requests: { method: string; body: unknown }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((_input: string | URL | Request, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      const body = init?.body ? JSON.parse(String(init.body)) : undefined;
      requests.push({ method, body });
      // The real endpoint accepts a snake_case body and always answers in
      // camelCase; translate the same way here so the mock behaves like it.
      const patched: Record<string, boolean> = {};
      if (body) {
        for (const [key, value] of Object.entries(body)) {
          if (key === "notify_reminder_emails") patched.notifyReminderEmails = value as boolean;
          if (key === "notify_round_published_emails") {
            patched.notifyRoundPublishedEmails = value as boolean;
          }
        }
      }
      const response = method === "PATCH" ? { ...initial, ...patched } : initial;
      return Promise.resolve(new Response(JSON.stringify(response), { status: 200 }));
    }),
  );
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <ToastProvider>
      <QueryClientProvider client={client}>
        <NotificationSettingsPanel />
      </QueryClientProvider>
    </ToastProvider>,
  );
  return requests;
}

describe("NotificationSettingsPanel", () => {
  it("loads saved preferences and sends a snake_case body when one is toggled off", async () => {
    const requests = renderPanel();

    expect(await screen.findByText("Deadline reminders")).toBeTruthy();
    const switches = screen.getAllByRole("switch");
    expect(switches).toHaveLength(2);
    expect(switches[0].getAttribute("aria-checked")).toBe("true");

    switches[0].click();

    await waitFor(() => expect(requests.some((request) => request.method === "PATCH")).toBe(true));
    const patchRequest = requests.find((request) => request.method === "PATCH");
    expect(patchRequest?.body).toEqual({ notify_reminder_emails: false });
    await waitFor(() => expect(switches[0].getAttribute("aria-checked")).toBe("false"));
  });
});
