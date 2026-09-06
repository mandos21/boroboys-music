import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Disc3, Eye, Headphones, Link2, ShieldCheck, Unplug } from "lucide-react";
import { Link } from "react-router";

import { api, del, patch } from "../../api/client";
import { StatePanel } from "../../components/ui/StatePanel";
import "./connections.css";

type Connection = {
  id: string;
  provider: "spotify" | "lastfm";
  displayName: string | null;
  visibility: "round_members" | "series_admins" | "private";
  isActive: boolean;
  disconnectedAt: string | null;
};

const providerInfo = {
  spotify: {
    description: "Search for tracks while submitting and choose a publisher for finished rounds.",
    icon: Disc3,
    name: "Spotify",
  },
  lastfm: {
    description: "Optionally share cached listening history with people in your rounds.",
    icon: Headphones,
    name: "Last.fm",
  },
} as const;

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
      <header className="page-heading settings-heading">
        <div>
          <p className="eyebrow">Account settings</p>
          <h1>Connected services</h1>
          <p>Bring the services you already use into your rounds. You stay in control of what is connected and what listening evidence is shared.</p>
        </div>
      </header>
      {connections.isLoading && <StatePanel kind="loading" title="Checking your connections">Looking for linked services.</StatePanel>}
      {connections.isError && <StatePanel kind="error" title="We couldn’t load your connections">Please refresh the page and try again.</StatePanel>}
      {!connections.isLoading && !connections.isError && (
        <div className="connection-grid">
          {(["spotify", "lastfm"] as const).map((provider) => {
            const connection = active.get(provider);
            const { description, icon: ProviderIcon, name } = providerInfo[provider];
            return (
              <section className={`panel connection-card ${connection ? "connection-active" : ""}`} key={provider}>
                <div className="connection-card-heading">
                  <span className="provider-icon" aria-hidden="true"><ProviderIcon size={22} /></span>
                  <div>
                    <p className="eyebrow">{name}</p>
                    <h2>{connection ? connection.displayName ?? "Connected" : `Connect ${name}`}</h2>
                  </div>
                </div>
                <p>{description}</p>
                {connection ? (
                  <div className="connection-controls">
                    <p className="connection-state"><ShieldCheck aria-hidden="true" size={16} /> Connected and ready</p>
                    {connection.provider === "lastfm" && (
                      <label className="connection-field">
                        <span><Eye aria-hidden="true" size={15} /> Listening evidence visibility</span>
                        <select value={connection.visibility} onChange={(event) => visibility.mutate({ id: connection.id, value: event.target.value as Connection["visibility"] })} disabled={visibility.isPending}>
                          <option value="round_members">Members in shared rounds</option>
                          <option value="series_admins">Series administrators only</option>
                          <option value="private">Only me</option>
                        </select>
                      </label>
                    )}
                    <button className="text-button danger connection-disconnect" type="button" disabled={disconnect.isPending} onClick={() => disconnect.mutate(connection.id)}>
                      <Unplug aria-hidden="true" size={16} /> Disconnect {name}
                    </button>
                  </div>
                ) : (
                  <a className="button connection-button" href={`/api/v1/connections/${provider}/login`}>
                    <Link2 aria-hidden="true" size={17} /> Connect {name}
                  </a>
                )}
              </section>
            );
          })}
        </div>
      )}
    </main>
  );
}
