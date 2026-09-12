import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Eye, Headphones, Link2, ShieldCheck, Unplug } from "lucide-react";
import { useSearchParams } from "react-router";

import { api, del, patch } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import type { components } from "../../api/schema";
import { ConfirmDialog } from "../../components/ui/ConfirmDialog";
import { StatePanel } from "../../components/ui/StatePanel";
import { useToast } from "../../components/ui/ToastProvider";
import { Button } from "../../components/ui/button";
import "./connections.css";

// Spotify search and track lookups run on the app's own credentials now (see
// backend/app/api/routes/rounds/discovery.py and _common.py), not a linked
// per-person Spotify account, because Spotify's Development Mode caps linked
// accounts far below what this group needs. Only the series publisher's own
// Spotify account (managed outside this page) is still used, for publishing
// finished rounds. Last.fm has no such cap, so it's still self-service here.
type Connection = components["schemas"]["ConnectionResponse"] & {
  provider: "lastfm";
  visibility: "round_members" | "series_admins" | "private";
};

const providerInfo = {
  lastfm: {
    description: "Optionally share cached listening history with people in your rounds.",
    icon: Headphones,
    name: "Last.fm",
  },
} as const;

const linkErrors: Record<string, string> = {
  denied:
    "The request was cancelled before the account was linked. You can try again whenever you like.",
  expired: "That linking request expired. Start it again from this page.",
  failed: "The provider did not complete the request. Try again in a moment.",
  "already-linked": "That account is already linked to a different person here.",
};

export function ConnectionsPanel() {
  const [searchParams] = useSearchParams();
  const linkError = searchParams.get("linkError");
  const linkErrorProvider = searchParams.get("provider");
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const [connectionToDisconnect, setConnectionToDisconnect] = useState<Connection | null>(null);
  const connections = useQuery({
    queryKey: queryKeys.connections(),
    // The series publisher's own account still shows up here as a "spotify"
    // connection; this page no longer manages that, so it's filtered out
    // below rather than rendered.
    queryFn: () =>
      api<(components["schemas"]["ConnectionResponse"] & { provider: "spotify" | "lastfm" })[]>(
        "/connections",
      ),
  });
  const invalidate = () => queryClient.invalidateQueries({ queryKey: queryKeys.connections() });
  const visibility = useMutation({
    mutationFn: ({ id, value }: { id: string; value: Connection["visibility"] }) =>
      patch(`/connections/${id}/visibility`, { visibility: value }),
    onSuccess: () => {
      invalidate();
      showToast({
        title: "Privacy setting saved",
        description: "Your listening-evidence visibility has been updated.",
      });
    },
    onError: () =>
      showToast({
        title: "Couldn’t save privacy setting",
        description: "Try again in a moment.",
        tone: "error",
      }),
  });
  const disconnect = useMutation({
    mutationFn: (id: string) => del(`/connections/${id}`),
    onSuccess: () => {
      invalidate();
      setConnectionToDisconnect(null);
      showToast({
        title: "Service disconnected",
        description: "You can link it again at any time.",
      });
    },
    onError: () =>
      showToast({
        title: "Couldn’t disconnect service",
        description: "Try again in a moment.",
        tone: "error",
      }),
  });
  const active = (connections.data ?? []).filter(
    (connection): connection is Connection =>
      connection.isActive && connection.provider === "lastfm",
  );
  const byProvider = (provider: Connection["provider"]) =>
    active.filter((connection) => connection.provider === provider);

  return (
    <>
      {linkError && (
        <StatePanel
          kind="error"
          title={`We couldn’t connect ${linkErrorProvider === "lastfm" ? "Last.fm" : "Spotify"}`}
        >
          {linkErrors[linkError] ??
            "The provider did not complete the request. Try again in a moment."}
        </StatePanel>
      )}
      {connections.isLoading && (
        <StatePanel kind="loading" title="Checking your connections">
          Looking for linked services.
        </StatePanel>
      )}
      {connections.isError && (
        <StatePanel kind="error" title="We couldn’t load your connections">
          Please refresh the page and try again.
        </StatePanel>
      )}
      {!connections.isLoading && !connections.isError && (
        <div className="connection-grid">
          {(["lastfm"] as const).map((provider) => {
            const linked = byProvider(provider);
            const { description, icon: ProviderIcon, name } = providerInfo[provider];
            return (
              <section
                className={`panel connection-card ${linked.length ? "connection-active" : ""}`}
                key={provider}
              >
                <div className="connection-card-heading">
                  <span className="provider-icon" aria-hidden="true">
                    <ProviderIcon size={22} />
                  </span>
                  <div>
                    <p className="eyebrow">{name}</p>
                    <h2>{linked.length ? name : `Connect ${name}`}</h2>
                  </div>
                </div>
                <p>{description}</p>
                {linked.map((connection) => (
                  <div className="connection-controls" key={connection.id}>
                    <p className="connection-state">
                      <ShieldCheck aria-hidden="true" size={16} />{" "}
                      {connection.displayName ?? "Connected"}
                    </p>
                    {connection.provider === "lastfm" && (
                      <label className="connection-field">
                        <span>
                          <Eye aria-hidden="true" size={15} /> Listening evidence visibility
                        </span>
                        <select
                          value={connection.visibility}
                          onChange={(event) =>
                            visibility.mutate({
                              id: connection.id,
                              value: event.target.value as Connection["visibility"],
                            })
                          }
                          disabled={visibility.isPending}
                        >
                          <option value="round_members">Members in shared rounds</option>
                          <option value="series_admins">Series administrators only</option>
                          <option value="private">Only me</option>
                        </select>
                      </label>
                    )}
                    <button
                      className="text-button danger connection-disconnect"
                      type="button"
                      disabled={disconnect.isPending}
                      onClick={() => setConnectionToDisconnect(connection)}
                    >
                      <Unplug aria-hidden="true" size={16} /> Disconnect{" "}
                      {connection.displayName ?? name}
                    </button>
                  </div>
                ))}
                <Button
                  className="connection-button"
                  render={<a href={`/api/v1/connections/${provider}/login`} />}
                >
                  <Link2 aria-hidden="true" size={17} />{" "}
                  {linked.length ? `Connect another ${name} account` : `Connect ${name}`}
                </Button>
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
        onOpenChange={(open) => {
          if (!open && !disconnect.isPending) setConnectionToDisconnect(null);
        }}
        onConfirm={() => {
          if (connectionToDisconnect) disconnect.mutate(connectionToDisconnect.id);
        }}
      />
    </>
  );
}
