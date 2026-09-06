import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router";

import { api, post } from "../../api/client";
import { formatDate } from "../../lib/format";
import { errorMessage } from "./adminUtils";
import type { AdminRound, Connection, Publication } from "./types";

export function PublicationPanel({
  round,
  onChanged,
}: {
  round: AdminRound;
  onChanged: () => void;
}) {
  const queryClient = useQueryClient();
  const publication = useQuery({
    queryKey: ["publication", round.id],
    queryFn: () =>
      api<Publication | null>(`/admin/rounds/${round.id}/publication`),
    retry: false,
  });
  const connections = useQuery({
    queryKey: ["connections"],
    queryFn: () => api<Connection[]>("/connections"),
    retry: false,
  });
  const [publisherId, setPublisherId] = useState("");
  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["publication", round.id] });
    onChanged();
  };
  const publish = useMutation({
    mutationFn: () =>
      post(`/admin/rounds/${round.id}/publish`, {
        publisher_account_id: publisherId,
      }),
    onSuccess: invalidate,
  });
  const unpublish = useMutation({
    mutationFn: () => post(`/admin/rounds/${round.id}/unpublish`, {}),
    onSuccess: invalidate,
  });
  const retry = useMutation({
    mutationFn: (publicationId: string) =>
      post(`/admin/publications/${publicationId}/retry`, {}),
    onSuccess: invalidate,
  });
  const spotifyAccounts = (connections.data ?? []).filter(
    (account) => account.provider === "spotify" && account.isActive,
  );
  const current = publication.data;
  const error =
    errorMessage(publish.error) ??
    errorMessage(unpublish.error) ??
    errorMessage(retry.error);
  return (
    <section className="panel publication-panel">
      <h2>Publication</h2>
      {publication.isLoading && <p>Loading publication status…</p>}
      {publication.isError && (
        <p className="error-message" role="alert">
          Publication status could not be loaded.
        </p>
      )}
      {!current && round.status === "closed" && (
        <>
          <p>
            Choose one of your linked Spotify accounts to publish this closed
            round.
          </p>
          {spotifyAccounts.length === 0 ? (
            <p>
              <Link to="/settings/connections">Link a Spotify account</Link>{" "}
              before publishing.
            </p>
          ) : (
            <>
              <label>
                Spotify publisher
                <select
                  value={publisherId}
                  onChange={(event) => setPublisherId(event.target.value)}
                >
                  <option value="">Choose an account</option>
                  {spotifyAccounts.map((account) => (
                    <option value={account.id} key={account.id}>
                      {account.displayName ?? "Spotify account"}
                    </option>
                  ))}
                </select>
              </label>
              <button
                className="button"
                type="button"
                disabled={!publisherId || publish.isPending}
                onClick={() => publish.mutate()}
              >
                {publish.isPending ? "Queueing…" : "Publish to Spotify"}
              </button>
            </>
          )}
        </>
      )}
      {!current && round.status !== "closed" && (
        <p>This round can be published after it has closed.</p>
      )}
      {current && (
        <>
          <p>
            <span className={`status ${current.state}`}>{current.state}</span>{" "}
            {current.isImported
              ? "Historical import"
              : `${current.attemptCount} publish attempt${current.attemptCount === 1 ? "" : "s"}`}
          </p>
          {current.spotifyPlaylistId && (
            <p>
              <a
                href={`https://open.spotify.com/playlist/${current.spotifyPlaylistId}`}
                target="_blank"
                rel="noreferrer"
              >
                Open Spotify playlist
              </a>
            </p>
          )}
          {current.lastError && (
            <p className="error-message" role="alert">
              {current.lastError}
            </p>
          )}
          {["publishing", "unpublishing"].includes(current.state) && (
            <p aria-live="polite">
              The worker is processing this publication. Refresh this page for
              the latest status.
            </p>
          )}
          {current.state === "failed" && (
            <button
              type="button"
              className="button"
              disabled={retry.isPending}
              onClick={() => retry.mutate(current.id)}
            >
              {retry.isPending
                ? "Retrying…"
                : current.retirementRequested
                  ? "Retry playlist retirement"
                  : "Retry publication"}
            </button>
          )}
          {round.status === "published" && !current.isImported && (
            <button
              type="button"
              className="danger-button"
              disabled={unpublish.isPending}
              onClick={() => unpublish.mutate()}
            >
              {unpublish.isPending
                ? "Queueing reversal…"
                : "Unpublish latest round"}
            </button>
          )}
          {round.status === "published" && current.isImported && (
            <p className="muted">
              Historical imports are retained and cannot be unpublished
              remotely.
            </p>
          )}
          {current.events.length > 0 && (
            <section className="publication-events">
              <h3>Audit history</h3>
              <ul>
                {current.events.map((event) => (
                  <li key={event.id}>
                    <strong>{event.action}</strong>
                    <span>{formatDate(event.createdAt)}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </>
      )}
      {error && (
        <p className="error-message" role="alert">
          {error}
        </p>
      )}
    </section>
  );
}
