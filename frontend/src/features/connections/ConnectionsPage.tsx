import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router";

import { api, del, patch } from "../../api/client";
import "./connections.css";

type Connection = {
  id: string;
  provider: "spotify" | "lastfm";
  displayName: string | null;
  visibility: "round_members" | "series_admins" | "private";
  isActive: boolean;
  disconnectedAt: string | null;
};

const providerName: Record<Connection["provider"], string> = {
  spotify: "Spotify",
  lastfm: "Last.fm",
};

export function ConnectionsPage() {
  const queryClient = useQueryClient();
  const connections = useQuery({
    queryKey: ["connections"],
    queryFn: () => api<Connection[]>("/connections"),
  });
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["connections"] });
  const visibility = useMutation({
    mutationFn: ({ id, value }: { id: string; value: Connection["visibility"] }) =>
      patch(`/connections/${id}/visibility`, { visibility: value }),
    onSuccess: invalidate,
  });
  const disconnect = useMutation({
    mutationFn: (id: string) => del(`/connections/${id}`),
    onSuccess: invalidate,
  });
  const active = new Map(
    (connections.data ?? [])
      .filter((connection) => connection.isActive)
      .map((connection) => [connection.provider, connection]),
  );

  return (
    <main className="shell settings-shell">
      <Link className="back" to="/">← Your rounds</Link>
      <header className="submission-heading">
        <p className="eyebrow">Account settings</p>
        <h1>Connected services</h1>
        <p>Spotify enables track search and publishing. Last.fm can share listening evidence using the privacy choice below.</p>
      </header>
      {connections.isLoading && <p>Loading connections…</p>}
      {connections.isError && <p className="error-message" role="alert">Connections could not be loaded. Please try again.</p>}
      <div className="connection-grid">
        {(["spotify", "lastfm"] as const).map((provider) => {
          const connection = active.get(provider);
          return (
            <section className="panel connection-card" key={provider}>
              <div>
                <p className="eyebrow">{providerName[provider]}</p>
                <h2>{connection ? connection.displayName ?? "Connected" : "Not connected"}</h2>
              </div>
              {!connection && <a className="button" href={`/api/v1/connections/${provider}/login`}>Connect {providerName[provider]}</a>}
              {connection?.provider === "lastfm" && (
                <label className="connection-field">Listening evidence visibility
                  <select value={connection.visibility} onChange={(event) => visibility.mutate({ id: connection.id, value: event.target.value as Connection["visibility"] })}>
                    <option value="round_members">Members in shared rounds</option>
                    <option value="series_admins">Series administrators only</option>
                    <option value="private">Only me</option>
                  </select>
                </label>
              )}
              {connection && <button className="text-button danger" type="button" disabled={disconnect.isPending} onClick={() => disconnect.mutate(connection.id)}>Disconnect</button>}
            </section>
          );
        })}
      </div>
    </main>
  );
}
