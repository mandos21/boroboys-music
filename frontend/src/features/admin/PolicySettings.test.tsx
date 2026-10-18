import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "../../components/ui/ToastProvider";
import { PolicySettings } from "./PolicySettings";

afterEach(() => vi.unstubAllGlobals());

describe("PolicySettings", () => {
  it.each([
    ["series", "/api/v1/admin/series/example", "default_policies"],
    ["round", "/api/v1/admin/rounds/example", "policy_snapshot"],
  ] as const)("saves %s checks through the existing policy editor", async (scope, path, field) => {
    const fetchMock = vi.fn(() => Promise.resolve(new Response("{}", { status: 200 })));
    vi.stubGlobal("fetch", fetchMock);
    render(
      <ToastProvider>
        <QueryClientProvider client={new QueryClient()}>
          <PolicySettings id="example" scope={scope} policies={[]} onSaved={() => {}} />
        </QueryClientProvider>
      </ToastProvider>,
    );
    const user = userEvent.setup();
    await user.selectOptions(screen.getByLabelText("Add a check"), "duplicate_in_series");
    await user.click(
      screen.getByRole("button", {
        name: scope === "round" ? "Save round checks" : "Save defaults",
      }),
    );

    await waitFor(() => expect(fetchMock).toHaveBeenCalledOnce());
    const [url, options] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe(path);
    expect(JSON.parse(String(options.body))[field]).toEqual([
      { kind: "duplicate_in_series", on_match: "reject" },
    ]);
  });
});
