import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "../../components/ui/ToastProvider";
import { SeriesCreatePanel } from "./SeriesCreatePanel";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("SeriesCreatePanel", () => {
  it("derives the full URL name until an administrator edits it", async () => {
    const user = userEvent.setup();
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <ToastProvider>
            <SeriesCreatePanel />
          </ToastProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await user.type(screen.getByLabelText("Name"), "Monthly favorites");
    await user.click(screen.getByText("Advanced options"));

    expect((screen.getByLabelText(/URL name/) as HTMLInputElement).value).toBe("monthly-favorites");
  });

  it("keeps the server's automatic-successor default when creating a series", async () => {
    const user = userEvent.setup();
    const fetchMock = vi
      .fn<(input: unknown, init?: RequestInit) => Promise<Response>>()
      .mockResolvedValue(new Response(JSON.stringify({ id: "series-1" }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <ToastProvider>
            <SeriesCreatePanel />
          </ToastProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await user.type(screen.getByLabelText("Name"), "New picks");
    await user.click(screen.getByRole("button", { name: "Create series" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const request = fetchMock.mock.calls[0]?.[1] as RequestInit;
    const body = JSON.parse(String(request.body));
    expect(body).toMatchObject({ name: "New picks", slug: "new-picks" });
    expect(body).not.toHaveProperty("auto_start_next_round");
  });
});
