import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";

import { ToastProvider } from "../../components/ui/ToastProvider";
import { SeriesCreatePanel } from "./SeriesCreatePanel";

describe("SeriesCreatePanel", () => {
  it("derives the full URL name until an administrator edits it", async () => {
    const user = userEvent.setup();
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <ToastProvider><SeriesCreatePanel /></ToastProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await user.type(screen.getByLabelText("Name"), "Monthly favorites");
    await user.click(screen.getByText("Advanced options"));

    expect((screen.getByLabelText("URL name") as HTMLInputElement).value).toBe("monthly-favorites");
  });
});
