import { useState } from "react";
import { useMutation } from "@tanstack/react-query";

import { post } from "../../api/client";
import { Button } from "../../components/ui/button";
import { useToast } from "../../components/ui/ToastProvider";
import { errorMessage } from "./adminUtils";

type Invite = { url: string; expiresAt: string; role: string; maxUses: number | null };

export function InvitePanel({ seriesId }: { seriesId: string }) {
  const { showToast } = useToast();
  const [role, setRole] = useState("contributor");
  const [days, setDays] = useState("7");
  const [link, setLink] = useState<string | null>(null);
  const create = useMutation({
    mutationFn: () =>
      post<Invite>(`/admin/series/${seriesId}/invites`, { role, expires_in_days: Number(days) }),
    onSuccess: (invite) => {
      setLink(invite.url);
      showToast({
        title: "Invite link ready",
        description: `It expires in ${days} day${days === "1" ? "" : "s"}.`,
      });
    },
    onError: (error) =>
      showToast({
        title: "Couldn’t create invite",
        description: errorMessage(error) ?? "Try again in a moment.",
        tone: "error",
      }),
  });
  async function copyLink() {
    if (!link) return;
    await navigator.clipboard.writeText(link);
    showToast({ title: "Invite copied", description: "Share it with the person you want to add." });
  }
  return (
    <section className="panel invite-panel">
      <h2>Invite someone</h2>
      <p className="field-hint">
        Invite links add people to this series. Admin links also grant management access.
      </p>
      <div className="invite-controls">
        <label>
          Role
          <select value={role} onChange={(event) => setRole(event.target.value)}>
            <option value="contributor">Contributor</option>
            <option value="admin">Series admin</option>
          </select>
        </label>
        <label>
          Expires in
          <select value={days} onChange={(event) => setDays(event.target.value)}>
            <option value="1">1 day</option>
            <option value="7">7 days</option>
            <option value="30">30 days</option>
          </select>
        </label>
        <Button
          type="button"
          variant="secondary"
          onClick={() => create.mutate()}
          disabled={create.isPending}
        >
          {create.isPending ? "Creating…" : "Create link"}
        </Button>
      </div>
      {link && (
        <div className="invite-link">
          <input readOnly value={link} aria-label="Invite link" />
          <button type="button" onClick={() => void copyLink()}>
            Copy
          </button>
        </div>
      )}
    </section>
  );
}
