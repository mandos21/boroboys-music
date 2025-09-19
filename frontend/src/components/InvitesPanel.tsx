import { useMemo } from "react";
import type { InviteRecord } from "../types";

type InvitesPanelProps = {
  invites: InviteRecord[];
  onRefresh: () => void;
  busy: boolean;
};

function InvitesPanel({ invites, onRefresh, busy }: InvitesPanelProps) {
  const sortedInvites = useMemo(() => invites.slice().sort((a, b) => (b.id ?? 0) - (a.id ?? 0)), [invites]);

  return (
    <section className="card">
      <div className="card__header">
        <h3>Active Invites</h3>
        <button className="secondary small" onClick={onRefresh} disabled={busy}>
          Refresh
        </button>
      </div>
      {sortedInvites.length === 0 ? (
        <p className="muted">No active invites yet. Generate one to onboard a new listener.</p>
      ) : (
        <div className="table">
          <div className="table__row table__row--head">
            <span>Token</span>
            <span>Email</span>
            <span>Role</span>
            <span>Expires</span>
          </div>
          {sortedInvites.map((invite) => (
            <div key={invite.id} className="table__row">
              <span className="token">{invite.token}</span>
              <span>{invite.email || "Any"}</span>
              <span className={invite.role === "admin" ? "pill pill--admin" : "pill"}>{invite.role}</span>
              <span>{invite.expires_at ? new Date(invite.expires_at).toLocaleString() : "No expiry"}</span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

export default InvitesPanel;
