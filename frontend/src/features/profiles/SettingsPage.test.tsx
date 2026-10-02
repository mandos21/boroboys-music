import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "../../components/ui/ToastProvider";
import { SettingsPage } from "./SettingsPage";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  window.localStorage.removeItem("music-rounds-palette");
  delete document.documentElement.dataset.palette;
});

function renderSettings() {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: string | URL | Request) => {
      const url = String(input);
      if (url.endsWith("/connections")) {
        return Promise.resolve(new Response(JSON.stringify([]), { status: 200 }));
      }
      if (url.endsWith("/profiles/me/notification-settings")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({ notifyReminderEmails: true, notifyRoundPublishedEmails: true }),
            { status: 200 },
          ),
        );
      }
      return Promise.resolve(new Response(JSON.stringify({}), { status: 200 }));
    }),
  );
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <ToastProvider>
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={["/settings"]}>
          <SettingsPage />
        </MemoryRouter>
      </QueryClientProvider>
    </ToastProvider>,
  );
}

describe("SettingsPage", () => {
  it("brings connected services and email notifications together, apart from the profile", async () => {
    renderSettings();

    expect(screen.getByRole("heading", { name: "Settings" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Connected services" })).toBeTruthy();
    expect(await screen.findByText("Deadline reminders")).toBeTruthy();
    expect(screen.getByRole("link", { name: /Your profile/ })).toHaveProperty(
      "href",
      expect.stringContaining("/profile"),
    );
  });

  it("saves and applies the distinguishable result palette", () => {
    renderSettings();
    const setting = screen.getByRole("switch", { name: /Distinguishable result colors/ });
    fireEvent.click(setting);
    expect(setting.getAttribute("aria-checked")).toBe("true");
    expect(document.documentElement.dataset.palette).toBe("colorblind");
    expect(window.localStorage.getItem("music-rounds-palette")).toBe("colorblind");
  });
});
