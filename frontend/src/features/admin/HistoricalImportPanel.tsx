import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Link } from "react-router";

import { api, post } from "../../api/client";
import { useToast } from "../../components/ui/ToastProvider";
import { errorMessage } from "./adminUtils";
import type { Connection } from "./types";

export function HistoricalImportPanel({
  seriesId,
  onImported,
}: {
  seriesId: string;
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
    mutationFn: () =>
      post<{ roundId: string }>(
        `/admin/series/${seriesId}/import-spotify-playlist`,
        {
          publisher_account_id: publisherId,
          spotify_playlist_id: playlistId,
          title: title.trim() || null,
          opens_at: new Date(opensAt).toISOString(),
          closes_at: new Date(closesAt).toISOString(),
          published_at: new Date(publishedAt).toISOString(),
        },
      ),
    onSuccess: () => {
      setPlaylistId("");
      setTitle("");
      onImported();
      showToast({ title: "Historical playlist imported", description: "It is now recorded as an immutable published round." });
    },
    onError: () => showToast({ title: "Couldn’t import playlist", description: "Check the playlist and account, then try again.", tone: "error" }),
  });
  const accounts = (connections.data ?? []).filter(
    (account) => account.provider === "spotify" && account.isActive,
  );
  return (
    <details className="panel historical-import">
      <summary>Import a historical Spotify playlist</summary>
      <p>
        Imports preserve the remote track order and create an immutable
        published round. Imported playlists are never retired remotely.
      </p>
      {accounts.length === 0 ? (
        <p>
          <Link to="/settings/connections">Link a Spotify account</Link> before
          importing.
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
