import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Link } from "react-router";

import { api, post } from "../../api/client";
import { useToast } from "../../components/ui/ToastProvider";
import { zonedInputToIso } from "../../lib/time";
import { errorMessage } from "./adminUtils";
import type { Connection } from "./types";

export function HistoricalImportPanel({
  seriesId,
  timezone,
  onImported,
}: {
  seriesId: string;
  timezone: string;
  onImported: () => void;
}) {
  const { showToast } = useToast();
  const [publisherId, setPublisherId] = useState("");
  const [playlistId, setPlaylistId] = useState("");
  const [title, setTitle] = useState("");
  const [opensAt, setOpensAt] = useState("");
  const [closesAt, setClosesAt] = useState("");
  const [publishedAt, setPublishedAt] = useState("");
  const connections = useQuery({
    queryKey: ["connections"],
    queryFn: () => api<Connection[]>("/connections"),
    retry: false,
  });
  const importPlaylist = useMutation({
    mutationFn: () => {
      const timestamps = {
        opens_at: zonedInputToIso(opensAt, timezone),
        closes_at: zonedInputToIso(closesAt, timezone),
        published_at: zonedInputToIso(publishedAt, timezone),
      };
      if (Object.values(timestamps).some((value) => value === null)) {
        throw new Error(`Those times are not valid in ${timezone}.`);
      }
      return post<{ roundId: string }>(`/admin/series/${seriesId}/import-spotify-playlist`, {
        publisher_account_id: publisherId,
        spotify_playlist_id: playlistId,
        title: title.trim() || null,
        ...timestamps,
      });
    },
    onSuccess: () => {
      setPlaylistId("");
      setTitle("");
      onImported();
      showToast({
        title: "Historical playlist imported",
        description: "It is now recorded as an immutable published round.",
      });
    },
    onError: () =>
      showToast({
        title: "Couldn’t import playlist",
        description: "Check the playlist and account, then try again.",
        tone: "error",
      }),
  });
  const accounts = (connections.data ?? []).filter(
    (account) => account.provider === "spotify" && account.isActive,
  );
  return (
    <details className="panel historical-import">
      <summary>Import a historical Spotify playlist</summary>
      <p>
        Imports preserve the remote track order and create an immutable published round. Imported
        playlists are never retired remotely. Times below are read in {timezone}, the series
        timezone.
      </p>
      {accounts.length === 0 ? (
        <p>
          <Link to="/settings/connections">Link a Spotify account</Link> before importing.
        </p>
      ) : (
        <form
          className="admin-round-form"
          onSubmit={(event) => {
            event.preventDefault();
            importPlaylist.mutate();
          }}
        >
          <label>
            Spotify publisher
            <select
              required
              value={publisherId}
              onChange={(event) => setPublisherId(event.target.value)}
            >
              <option value="">Choose an account</option>
              {accounts.map((account) => (
                <option key={account.id} value={account.id}>
                  {account.displayName ?? "Spotify account"}
                </option>
              ))}
            </select>
          </label>
          <label>
            Playlist ID
            <input
              required
              value={playlistId}
              placeholder="Spotify playlist ID"
              maxLength={128}
              onChange={(event) => setPlaylistId(event.target.value)}
            />
          </label>
          <label>
            Round title (optional)
            <input
              value={title}
              maxLength={200}
              onChange={(event) => setTitle(event.target.value)}
            />
          </label>
          <label>
            Opened
            <input
              type="datetime-local"
              required
              value={opensAt}
              onChange={(event) => setOpensAt(event.target.value)}
            />
          </label>
          <label>
            Closed
            <input
              type="datetime-local"
              required
              value={closesAt}
              onChange={(event) => setClosesAt(event.target.value)}
            />
          </label>
          <label>
            Published
            <input
              type="datetime-local"
              required
              value={publishedAt}
              onChange={(event) => setPublishedAt(event.target.value)}
            />
          </label>
          <button className="button" disabled={importPlaylist.isPending}>
            {importPlaylist.isPending ? "Importing…" : "Import playlist"}
          </button>
          {errorMessage(importPlaylist.error) && (
            <p className="error-message" role="alert">
              {errorMessage(importPlaylist.error)}
            </p>
          )}
        </form>
      )}
    </details>
  );
}
