import { afterEach, describe, expect, it, vi } from "vitest";

import { api } from "./client";

const originalDocument = globalThis.document;
const originalFetch = globalThis.fetch;

afterEach(() => {
  Object.defineProperty(globalThis, "document", { configurable: true, value: originalDocument });
  Object.defineProperty(globalThis, "fetch", { configurable: true, value: originalFetch });
  vi.restoreAllMocks();
});

describe("API client", () => {
  it("sends the CSRF cookie value and browser credentials with every request", async () => {
    Object.defineProperty(globalThis, "document", {
      configurable: true,
      value: { cookie: "music_rounds_session_csrf=csrf%20value" },
    });
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ status: "ok" }), { status: 200 }),
    );
    Object.defineProperty(globalThis, "fetch", { configurable: true, value: fetchMock });

    await expect(api<{ status: string }>("/health")).resolves.toEqual({ status: "ok" });
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/health",
      expect.objectContaining({ credentials: "include" }),
    );
    const request = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(new Headers(request.headers).get("X-CSRF-Token")).toBe("csrf value");
  });

  it("turns API errors into an actionable typed error", async () => {
    Object.defineProperty(globalThis, "document", { configurable: true, value: { cookie: "" } });
    Object.defineProperty(globalThis, "fetch", {
      configurable: true,
      value: vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "round membership required" }), { status: 403 }),
      ),
    });

    await expect(api("/rounds/not-yours")).rejects.toEqual(
      expect.objectContaining({ status: 403, message: "round membership required" }),
    );
  });
});
