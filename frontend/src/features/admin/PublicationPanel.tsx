import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router";

import { api, post } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import { Button } from "../../components/ui/button";
import { ConfirmDialog } from "../../components/ui/ConfirmDialog";
import { StatePanel } from "../../components/ui/StatePanel";
import { useToast } from "../../components/ui/ToastProvider";
import { formatDate } from "../../lib/format";
import { errorMessage } from "./adminUtils";
import type { AdminRound, Connection, Publication } from "./types";

const IN_FLIGHT_STATES = ["pending", "publishing", "unpublishing"];

export function PublicationPanel({
  round,
  onChanged,
}: {
  round: AdminRound;
  onChanged: () => void;
}) {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  // Held in a ref so the settle effect below does not re-run whenever the
  // parent passes a new callback identity. Assigned in an effect rather than
  // during render, which is not a safe time to touch a ref.
  const onChangedRef = useRef(onChanged);
  useEffect(() => {
    onChangedRef.current = onChanged;
  });
  const publication = useQuery({
    queryKey: queryKeys.publication(round.id),
    queryFn: () => api<Publication | null>(`/admin/rounds/${round.id}/publication`),
    retry: false,
    refetchInterval: (query) =>
      IN_FLIGHT_STATES.includes(query.state.data?.state ?? "") ? 5_000 : false,
  });
  // The round's own status changes with the publication's. Without this the
  // page would still believe the round was publishing after the poll settled.
  const publicationState = publication.data?.state;
  const previousState = useRef(publicationState);
  useEffect(() => {
    const settled = Boolean(publicationState) && !IN_FLIGHT_STATES.includes(publicationState ?? "");
    if (settled && previousState.current && IN_FLIGHT_STATES.includes(previousState.current)) {
      onChangedRef.current();
    }
    previousState.current = publicationState;
  }, [publicationState]);
  const connections = useQuery({
    queryKey: queryKeys.connections(),
    queryFn: () => api<Connection[]>("/connections"),
    retry: false,
  });
  const [publisherId, setPublisherId] = useState("");
  const [unpublishRequested, setUnpublishRequested] = useState(false);
  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: queryKeys.publication(round.id) });
    onChanged();
  };
  const publish = useMutation({
    mutationFn: () =>
      post(`/admin/rounds/${round.id}/publish`, {
        publisher_account_id: publisherId,
      }),
    onSuccess: () => {
      invalidate();
      showToast({
        title: "Publication queued",
        description: "BoroCrew Music is creating the Spotify playlist in the background.",
      });
    },
  });
  const unpublish = useMutation({
    mutationFn: () => post(`/admin/rounds/${round.id}/unpublish`, {}),
    onSuccess: () => {
      invalidate();
      setUnpublishRequested(false);
      showToast({
        title: "Playlist retirement queued",
        description:
          "The latest playlist will be removed before the round returns to its prior state.",
      });
    },
  });
  const retry = useMutation({
    mutationFn: (publicationId: string) => post(`/admin/publications/${publicationId}/retry`, {}),
    onSuccess: () => {
      invalidate();
      showToast({
        title: "Publication retry queued",
        description: "The worker will attempt the operation again shortly.",
      });
    },
  });
  const spotifyAccounts = (connections.data ?? []).filter(
    (account) => account.provider === "spotify" && account.isActive,
  );
  const current = publication.data;
  const stateDescription =
    current &&
    {
      pending: "The worker will begin this publication shortly.",
      publishing:
        "Creating and populating the Spotify playlist. This page refreshes automatically while it runs.",
      published: "The playlist is published and available to the group.",
      failed: "The last attempt did not finish. Review the message below, then retry when ready.",
      unpublishing:
        "Removing the Spotify playlist from the publisher’s library and returning the round to its prior state. This page refreshes automatically while it runs.",
      unpublished:
        "This release was unpublished. You can publish the immutable round snapshot again.",
    }[current.state];
  const error =
    errorMessage(publish.error) ?? errorMessage(unpublish.error) ?? errorMessage(retry.error);
  return (
    <section className="panel publication-panel">
      <h2>Publication</h2>
      {publication.isLoading && (
        <StatePanel kind="loading" title="Loading publication status">
          Checking the playlist and its activity history.
        </StatePanel>
      )}
      {publication.isError && (
        <StatePanel kind="error" title="We couldn’t load publication status">
          Refresh the page to see the latest Spotify activity.
        </StatePanel>
      )}
      {(!current || current.state === "unpublished") && round.status === "closed" && (
        <>
          <p>
            Choose one of your linked Spotify accounts to publish this closed round
            {current ? " again" : ""}.
          </p>
          {spotifyAccounts.length === 0 ? (
            <p>
              <Link to="/settings/connections">Link a Spotify account</Link> before publishing.
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
              <Button
                type="button"
                disabled={!publisherId || publish.isPending}
                onClick={() => publish.mutate()}
              >
                {publish.isPending ? "Queueing…" : current ? "Publish again" : "Publish to Spotify"}
              </Button>
            </>
          )}
        </>
      )}
      {!current && round.status !== "closed" && (
        <p>
          This round can be published after it has closed.
          {round.publisherAccountId
            ? ` It will publish itself at ${formatDate(round.publishAt)}.`
            : " Choose a publishing account in its round settings to release it automatically."}
        </p>
      )}
      {!current && round.status === "closed" && round.publisherAccountId && (
        <p className="field-hint">
          This round is scheduled to publish itself. You can also release it now.
        </p>
      )}
      {current && (
        <>
          <p>
            <span className={`status ${current.state}`}>{current.state}</span>{" "}
            {current.isImported
              ? "Historical import"
              : `${current.attemptCount} publish attempt${current.attemptCount === 1 ? "" : "s"}`}
          </p>
          {stateDescription && (
            <p
              className="publication-state-copy"
              aria-live={
                ["publishing", "unpublishing"].includes(current.state) ? "polite" : undefined
              }
            >
              {stateDescription}
            </p>
          )}
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
          {current.state === "failed" && (
            <Button
              type="button"
              disabled={retry.isPending}
              onClick={() => retry.mutate(current.id)}
            >
              {retry.isPending
                ? "Retrying…"
                : current.retirementRequested
                  ? "Retry playlist retirement"
                  : "Retry publication"}
            </Button>
          )}
          {round.status === "published" && !current.isImported && (
            <Button
              type="button"
              variant="destructive"
              disabled={unpublish.isPending}
              onClick={() => setUnpublishRequested(true)}
            >
              {unpublish.isPending ? "Queueing reversal…" : "Unpublish latest round"}
            </Button>
          )}
          {round.status === "published" && current.isImported && (
            <p className="muted">
              Historical imports are retained and cannot be unpublished remotely.
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
      <ConfirmDialog
        open={unpublishRequested}
        title="Unpublish this latest round?"
        description="BoroCrew Music will remove the associated Spotify playlist from the publisher’s library and return the round to its prior state. This is only available for the most recently published round."
        confirmLabel="Unpublish playlist"
        isPending={unpublish.isPending}
        onOpenChange={(open) => {
          if (!open && !unpublish.isPending) setUnpublishRequested(false);
        }}
        onConfirm={() => unpublish.mutate()}
      />
    </section>
  );
}
