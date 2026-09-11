import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "../../components/ui/ToastProvider";
import { NotificationSettingsPanel } from "./NotificationSettingsPanel";

afterEach(() => vi.restoreAllMocks());

type Deferred = { resolve: () => void };

function renderPanel(options: { holdSecondGet?: Deferred } = {}) {
  const initial = { notifyReminderEmails: true, notifyRoundPublishedEmails: true };
  const requests: { method: string; body: unknown }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((_input: string | URL | Request, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      const body = init?.body ? JSON.parse(String(init.body)) : undefined;
      requests.push({ method, body });
      const getCount = requests.filter((request) => request.method === "GET").length;
      if (method === "GET" && getCount === 2 && options.holdSecondGet) {
        // A refetch that started before the PATCH and answers after it, with
        // the values from before the change.
        return new Promise<Response>((resolve) => {
          options.holdSecondGet!.resolve = () =>
            resolve(new Response(JSON.stringify(initial), { status: 200 }));
        });
      }
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
  return { requests, client };
}

describe("NotificationSettingsPanel", () => {
  it("loads saved preferences and sends a snake_case body when one is toggled off", async () => {
    const { requests } = renderPanel();

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

  it("does not let a refetch that started before the change overwrite the saved value", async () => {
    const held: Deferred = { resolve: () => undefined };
    const { requests, client } = renderPanel({ holdSecondGet: held });
    expect(await screen.findByText("Deadline reminders")).toBeTruthy();
    const switches = screen.getAllByRole("switch");

    // A window-focus style refetch is in flight when the person toggles.
    void client.refetchQueries({ queryKey: ["notification-settings"] });
    await waitFor(() =>
      expect(requests.filter((request) => request.method === "GET")).toHaveLength(2),
    );
    switches[0].click();
    await waitFor(() => expect(switches[0].getAttribute("aria-checked")).toBe("false"));

    held.resolve();
    await new Promise((resolve) => setTimeout(resolve, 20));

    expect(switches[0].getAttribute("aria-checked")).toBe("false");
  });
});
