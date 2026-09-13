import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { RoundPage } from "./RoundPages";
import { ToastProvider } from "../../components/ui/ToastProvider";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

function renderRound() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <ToastProvider>
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={["/rounds/round-1"]}>
          <Routes>
            <Route path="/rounds/:roundId" element={<RoundPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </ToastProvider>,
  );
}

function stubRoundFetch(round: Record<string, unknown>) {
  const requests: { url: string; method: string; body: unknown }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((input: string | URL | Request, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      const body = init?.body ? JSON.parse(String(init.body)) : undefined;
      requests.push({ url, method, body });
      if (url.endsWith("/rounds/round-1/participation")) {
        round = { ...round, declinedFurtherSubmissions: body.declined_further_submissions };
        return Promise.resolve(
          new Response(
            JSON.stringify({ declinedFurtherSubmissions: round.declinedFurtherSubmissions }),
            { status: 200 },
          ),
        );
      }
      if (url.endsWith("/rounds/round-1")) {
        return Promise.resolve(new Response(JSON.stringify(round), { status: 200 }));
      }
      return Promise.resolve(new Response(JSON.stringify([]), { status: 200 }));
    }),
  );
  return requests;
}

const baseRound = {
  id: "round-1",
  title: "September picks",
  status: "open",
  opensAt: "2026-09-01T00:00:00Z",
  closesAt: "2026-09-30T00:00:00Z",
  publishAt: "2026-10-01T00:00:00Z",
  submissionLimit: 2,
  canManage: false,
  isMember: true,
  declinedFurtherSubmissions: false,
};

describe("RoundPage", () => {
  it("offers a clear submission action only while the round is open", async () => {
    stubRoundFetch(baseRound);

    renderRound();

    expect(await screen.findByRole("heading", { name: "September picks" })).toBeTruthy();
    expect(await screen.findByRole("link", { name: "Choose a track" })).toHaveProperty(
      "href",
      expect.stringContaining("/rounds/round-1/submit"),
    );
    expect(await screen.findByRole("heading", { name: "Submissions" })).toBeTruthy();
  });

  it("waits for the submission list before offering capacity-dependent controls", async () => {
    let releaseSubmissions: (entries: unknown[]) => void = () => undefined;
    vi.stubGlobal(
      "fetch",
      vi.fn((input: string | URL | Request) => {
        const url = String(input);
        if (url.endsWith("/rounds/round-1/submissions")) {
          return new Promise<Response>((resolve) => {
            releaseSubmissions = (entries) =>
              resolve(new Response(JSON.stringify(entries), { status: 200 }));
          });
        }
        if (url.endsWith("/rounds/round-1/submission-counts")) {
          return Promise.resolve(new Response(JSON.stringify([]), { status: 200 }));
        }
        return Promise.resolve(new Response(JSON.stringify(baseRound), { status: 200 }));
      }),
    );

    renderRound();

    expect(await screen.findByRole("heading", { name: "September picks" })).toBeTruthy();
    expect(screen.getByText("Checking how much room you have left in this round.")).toBeTruthy();
    expect(screen.queryByRole("link", { name: "Choose a track" })).toBeNull();
    expect(screen.queryByRole("switch")).toBeNull();

    const mine = (id: string) => ({
      id,
      status: "accepted",
      note: null,
      createdAt: "2026-09-02T00:00:00Z",
      updatedAt: "2026-09-02T00:00:00Z",
      withdrawnAt: null,
      isMine: true,
      contributor: { id: "me", displayName: "Me", spotifyProfileImageUrl: null },
      track: { spotifyTrackId: id, name: id, artist: "A", album: null, spotifyUri: null },
    });
    releaseSubmissions([mine("one"), mine("two")]);

    expect(await screen.findByText(/You.re all set!/)).toBeTruthy();
    expect(screen.queryByRole("link", { name: "Choose a track" })).toBeNull();
    expect(screen.queryByRole("switch")).toBeNull();
  });

  it("offers no contributor controls to an administrator who is not a member", async () => {
    stubRoundFetch({ ...baseRound, canManage: true, isMember: false });

    renderRound();

    expect(await screen.findByRole("heading", { name: "September picks" })).toBeTruthy();
    expect(await screen.findByText(/aren.t one of its contributors/)).toBeTruthy();
    expect(screen.queryByRole("link", { name: "Choose a track" })).toBeNull();
    expect(screen.queryByRole("switch")).toBeNull();
    expect(screen.getByRole("link", { name: "Manage this round" })).toBeTruthy();
  });

  it("lets a member declare they're done submitting, without losing their pick capacity", async () => {
    const requests = stubRoundFetch(baseRound);

    renderRound();

    expect(await screen.findByText("I'm not submitting any more this round")).toBeTruthy();
    const toggle = screen.getByRole("switch");
    expect(toggle.getAttribute("aria-checked")).toBe("false");

    toggle.click();

    await waitFor(() =>
      expect(requests.some((request) => request.url.endsWith("/participation"))).toBe(true),
    );
    const participationRequest = requests.find((request) => request.url.endsWith("/participation"));
    expect(participationRequest?.method).toBe("PATCH");
    expect(participationRequest?.body).toEqual({ declined_further_submissions: true });
    await waitFor(() =>
      expect(screen.getByText(/you won.t get deadline reminders for it/).textContent).toBeTruthy(),
    );
    // The PATCH response is enough to update the page; nothing is refetched.
    expect(requests.filter((request) => request.method === "GET").map((r) => r.url)).toEqual(
      requests
        .filter((request) => request.method === "GET")
        .map((r) => r.url)
        .filter((url, index, urls) => urls.indexOf(url) === index),
    );
    expect(toggle.getAttribute("aria-checked")).toBe("true");
  });

  it("hides other contributors' picks while the round is open, showing counts instead", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: string | URL | Request) => {
        const url = String(input);
        if (url.endsWith("/rounds/round-1/submissions")) {
          return Promise.resolve(
            new Response(
              JSON.stringify([
                {
                  id: "mine",
                  status: "accepted",
                  note: null,
                  createdAt: "2026-09-02T00:00:00Z",
                  updatedAt: "2026-09-02T00:00:00Z",
                  withdrawnAt: null,
                  isMine: true,
                  contributor: { id: "me", displayName: "Me", spotifyProfileImageUrl: null },
                  track: {
                    spotifyTrackId: "mine",
                    name: "My Song",
                    artist: "A",
                    album: null,
                    spotifyUri: null,
                  },
                },
              ]),
              { status: 200 },
            ),
          );
        }
        if (url.endsWith("/rounds/round-1/submission-counts")) {
          return Promise.resolve(
            new Response(
              JSON.stringify([
                {
                  contributor: { id: "me", displayName: "Me", spotifyProfileImageUrl: null },
                  count: 1,
                },
                {
                  contributor: {
                    id: "friend",
                    displayName: "Friend",
                    spotifyProfileImageUrl: null,
                  },
                  count: 2,
                },
              ]),
              { status: 200 },
            ),
          );
        }
        return Promise.resolve(new Response(JSON.stringify(baseRound), { status: 200 }));
      }),
    );

    renderRound();

    expect(await screen.findByText("My Song")).toBeTruthy();
    // The other contributor shows up only as a count, never a track.
    expect(screen.getByText("Friend")).toBeTruthy();
    expect(screen.queryByText(/Friend.*Song/)).toBeNull();
  });

  it("keeps the note editor collapsed until 'Edit note' is clicked, then saves it", async () => {
    const user = userEvent.setup();
    const requests: { url: string; method: string; body: unknown }[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn((input: string | URL | Request, init?: RequestInit) => {
        const url = String(input);
        const method = init?.method ?? "GET";
        requests.push({
          url,
          method,
          body: init?.body ? JSON.parse(String(init.body)) : undefined,
        });
        if (url.endsWith("/rounds/round-1/submissions")) {
          return Promise.resolve(
            new Response(
              JSON.stringify([
                {
                  id: "mine",
                  status: "accepted",
                  note: "Original note",
                  createdAt: "2026-09-02T00:00:00Z",
                  updatedAt: "2026-09-02T00:00:00Z",
                  withdrawnAt: null,
                  isMine: true,
                  contributor: { id: "me", displayName: "Me", spotifyProfileImageUrl: null },
                  track: {
                    spotifyTrackId: "mine",
                    name: "My Song",
                    artist: "A",
                    album: null,
                    spotifyUri: null,
                  },
                },
              ]),
              { status: 200 },
            ),
          );
        }
        if (url.endsWith("/rounds/round-1/submission-counts")) {
          return Promise.resolve(new Response(JSON.stringify([]), { status: 200 }));
        }
        if (url.endsWith("/rounds/submissions/mine")) {
          return Promise.resolve(new Response(JSON.stringify(null), { status: 200 }));
        }
        return Promise.resolve(new Response(JSON.stringify(baseRound), { status: 200 }));
      }),
    );

    renderRound();

    expect(await screen.findByText("My Song")).toBeTruthy();
    expect(screen.queryByLabelText("Note")).toBeNull();

    await user.click(screen.getByRole("button", { name: "Edit note" }));
    const textarea = screen.getByLabelText("Note") as HTMLTextAreaElement;
    expect(textarea.value).toBe("Original note");

    await user.clear(textarea);
    await user.type(textarea, "Updated note");
    await user.click(screen.getByRole("button", { name: "Save note" }));

    await waitFor(() =>
      expect(requests.some((request) => request.url.endsWith("/rounds/submissions/mine"))).toBe(
        true,
      ),
    );
    const saveRequest = requests.find((request) =>
      request.url.endsWith("/rounds/submissions/mine"),
    );
    expect(saveRequest?.method).toBe("PATCH");
    expect(saveRequest?.body).toEqual({ note: "Updated note" });

    // The editor collapses back down after saving.
    expect(screen.queryByLabelText("Note")).toBeNull();
  });
});
