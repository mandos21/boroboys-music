import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Disc3, Eye, Headphones, Link2, ShieldCheck, Unplug } from "lucide-react";
import { Link, useSearchParams } from "react-router";

import { api, del, patch } from "../../api/client";
import type { components } from "../../api/schema";
import { ConfirmDialog } from "../../components/ui/ConfirmDialog";
import { StatePanel } from "../../components/ui/StatePanel";
import { useToast } from "../../components/ui/ToastProvider";
import "./connections.css";

type Connection = components["schemas"]["ConnectionResponse"] & {
  provider: "spotify" | "lastfm";
  visibility: "round_members" | "series_admins" | "private";
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

const linkErrors: Record<string, string> = {
  denied: "The request was cancelled before the account was linked. You can try again whenever you like.",
  expired: "That linking request expired. Start it again from this page.",
  failed: "The provider did not complete the request. Try again in a moment.",
  "already-linked": "That account is already linked to a different person here.",
};

export function ConnectionsPage() {
  const [searchParams] = useSearchParams();
  const linkError = searchParams.get("linkError");
  const linkErrorProvider = searchParams.get("provider");
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const [connectionToDisconnect, setConnectionToDisconnect] = useState<Connection | null>(null);
  const connections = useQuery({
    queryKey: ["connections"],
    queryFn: () => api<Connection[]>("/connections"),
  });
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["connections"] });
  const visibility = useMutation({
    mutationFn: ({ id, value }: { id: string; value: Connection["visibility"] }) =>
      patch(`/connections/${id}/visibility`, { visibility: value }),
    onSuccess: () => {
      invalidate();
      showToast({ title: "Privacy setting saved", description: "Your listening-evidence visibility has been updated." });
    },
    onError: () => showToast({ title: "Couldn’t save privacy setting", description: "Try again in a moment.", tone: "error" }),
  });
  const disconnect = useMutation({
    mutationFn: (id: string) => del(`/connections/${id}`),
    onSuccess: () => {
      invalidate();
      setConnectionToDisconnect(null);
      showToast({ title: "Service disconnected", description: "You can link it again at any time." });
    },
    onError: () => showToast({ title: "Couldn’t disconnect service", description: "Try again in a moment.", tone: "error" }),
  });
  // A person may link more than one account for a provider, and each one has
  // to stay individually visible so it can be inspected or disconnected.
  const active = (connections.data ?? []).filter((connection) => connection.isActive);
  const byProvider = (provider: Connection["provider"]) =>
    active.filter((connection) => connection.provider === provider);

  return (
    <main className="shell settings-shell">
      <Link className="back" to="/">← Your series</Link>
      <header className="page-heading settings-heading">
        <div>
          <p className="eyebrow">Your profile</p>
          <h1>Profile &amp; connected services</h1>
          <p>Bring the services you already use into your series. You stay in control of what is connected and what listening evidence is shared.</p>
        </div>
      </header>
      {linkError && (
        <StatePanel kind="error" title={`We couldn’t connect ${linkErrorProvider === "lastfm" ? "Last.fm" : "Spotify"}`}>
          {linkErrors[linkError] ?? "The provider did not complete the request. Try again in a moment."}
        </StatePanel>
      )}
      {connections.isLoading && <StatePanel kind="loading" title="Checking your connections">Looking for linked services.</StatePanel>}
      {connections.isError && <StatePanel kind="error" title="We couldn’t load your connections">Please refresh the page and try again.</StatePanel>}
      {!connections.isLoading && !connections.isError && (
        <div className="connection-grid">
          {(["spotify", "lastfm"] as const).map((provider) => {
            const linked = byProvider(provider);
            const { description, icon: ProviderIcon, name } = providerInfo[provider];
            return (
              <section className={`panel connection-card ${linked.length ? "connection-active" : ""}`} key={provider}>
                <div className="connection-card-heading">
                  <span className="provider-icon" aria-hidden="true"><ProviderIcon size={22} /></span>
                  <div>
                    <p className="eyebrow">{name}</p>
                    <h2>{linked.length ? name : `Connect ${name}`}</h2>
                  </div>
                </div>
                <p>{description}</p>
                {linked.map((connection) => (
                  <div className="connection-controls" key={connection.id}>
                    <p className="connection-state"><ShieldCheck aria-hidden="true" size={16} /> {connection.displayName ?? "Connected"}</p>
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
                    <button className="text-button danger connection-disconnect" type="button" disabled={disconnect.isPending} onClick={() => setConnectionToDisconnect(connection)}>
                      <Unplug aria-hidden="true" size={16} /> Disconnect {connection.displayName ?? name}
                    </button>
                  </div>
                ))}
                <a className="button connection-button" href={`/api/v1/connections/${provider}/login`}>
                  <Link2 aria-hidden="true" size={17} /> {linked.length ? `Connect another ${name} account` : `Connect ${name}`}
                </a>
              </section>
            );
          })}
        </div>
      )}
      <ConfirmDialog
        open={Boolean(connectionToDisconnect)}
        title={`Disconnect ${connectionToDisconnect ? providerInfo[connectionToDisconnect.provider].name : "service"}?`}
        description="This removes its stored connection from BoroCrew Music. Your provider account and past round history are not deleted."
        confirmLabel="Disconnect service"
        isPending={disconnect.isPending}
        onOpenChange={(open) => { if (!open && !disconnect.isPending) setConnectionToDisconnect(null); }}
        onConfirm={() => { if (connectionToDisconnect) disconnect.mutate(connectionToDisconnect.id); }}
      />
    </main>
  );
}
