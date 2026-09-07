import { useDeferredValue, useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router";

import { api, del, patch, put } from "../../api/client";
import { ConfirmDialog } from "../../components/ui/ConfirmDialog";
import { useToast } from "../../components/ui/ToastProvider";
import { PublicationPanel } from "./PublicationPanel";
import { errorMessage } from "./adminUtils";
import type { AdminRound, User } from "./types";

function dateTimeInput(value: string) {
  const date = new Date(value);
  const offset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}

export function AdminRoundPage() {
  const { roundId } = useParams();
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const detail = useQuery({
    queryKey: ["admin-round", roundId],
    queryFn: () => api<AdminRound>(`/admin/rounds/${roundId}`),
    enabled: Boolean(roundId),
    retry: false,
  });
  const [search, setSearch] = useState("");
  const [newLimit, setNewLimit] = useState("");
  const [overrides, setOverrides] = useState<Record<string, string>>({});
  const [memberToRemove, setMemberToRemove] = useState<User | null>(null);
  const [title, setTitle] = useState("");
  const [opensAt, setOpensAt] = useState("");
  const [closesAt, setClosesAt] = useState("");
  const [publishAt, setPublishAt] = useState("");
  const [submissionLimit, setSubmissionLimit] = useState("");
  const [prompt, setPrompt] = useState("");
  const [promptEdited, setPromptEdited] = useState(false);
  const deferredSearch = useDeferredValue(search.trim());
  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ["admin-round", roundId] });
  const users = useQuery({
    queryKey: ["round-users", detail.data?.seriesId, deferredSearch],
    queryFn: () =>
      api<User[]>(
        `/admin/series/${detail.data?.seriesId}/users?query=${encodeURIComponent(deferredSearch)}`,
      ),
    enabled: Boolean(detail.data?.seriesId) && deferredSearch.length >= 2,
  });
  const saveMember = useMutation({
    mutationFn: ({ userId, value }: { userId: string; value: string }) =>
      put(`/admin/rounds/${roundId}/members/${userId}`, {
        submission_limit_override: value === "" ? null : Number(value),
      }),
    onSuccess: () => {
      invalidate();
      showToast({ title: "Contributor updated", description: "Their round access and submission limit are saved." });
    },
    onError: () => showToast({ title: "Couldn’t update contributor", description: "Try again in a moment.", tone: "error" }),
  });
  const removeMember = useMutation({
    mutationFn: (userId: string) =>
      del(`/admin/rounds/${roundId}/members/${userId}`),
    onSuccess: () => {
      invalidate();
      setMemberToRemove(null);
      showToast({ title: "Contributor removed", description: "Their existing submissions remain attributable in this round." });
    },
    onError: () => showToast({ title: "Couldn’t remove contributor", description: "Try again in a moment.", tone: "error" }),
  });
  const saveRound = useMutation({
    mutationFn: (payload: Record<string, unknown>) => patch(`/admin/rounds/${roundId}`, payload),
    onSuccess: () => {
      invalidate();
      showToast({ title: "Round settings saved", description: "The schedule and submission limit are updated." });
    },
    onError: (error) => showToast({ title: "Couldn’t save round settings", description: errorMessage(error) ?? "Try again in a moment.", tone: "error" }),
  });
  if (detail.isLoading)
    return (
      <main className="shell">
        <p>Loading round contributors…</p>
      </main>
    );
  if (detail.isError || !detail.data)
    return (
      <main className="shell">
        <section className="panel">
          <h1>Round unavailable</h1>
          <Link to="/admin">Return to series</Link>
        </section>
      </main>
    );
  const round = detail.data;
  const membershipEditable = ["draft", "scheduled", "open"].includes(
    round.status,
  );
  const openingEditable = ["draft", "scheduled"].includes(round.status);
  const selectedTitle = title || round.title;
  const selectedOpensAt = opensAt || dateTimeInput(round.opensAt);
  const selectedClosesAt = closesAt || dateTimeInput(round.closesAt);
  const selectedPublishAt = publishAt || dateTimeInput(round.publishAt);
  const selectedLimit = submissionLimit || String(round.submissionLimit);
  const selectedPrompt = promptEdited ? prompt : round.prompt ?? "";
  function submitSettings(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedTitle.trim()) return showToast({ title: "Add a round title", tone: "error" });
    if (new Date(selectedOpensAt) >= new Date(selectedClosesAt)) return showToast({ title: "Closing must follow opening", tone: "error" });
    if (new Date(selectedClosesAt) > new Date(selectedPublishAt)) return showToast({ title: "Publish after the round closes", tone: "error" });
    saveRound.mutate({
      title: selectedTitle,
      ...(openingEditable ? { opens_at: new Date(selectedOpensAt).toISOString() } : {}),
      closes_at: new Date(selectedClosesAt).toISOString(),
      publish_at: new Date(selectedPublishAt).toISOString(),
      submission_limit: Number(selectedLimit),
      prompt: selectedPrompt.trim() || null,
    });
  }
  return (
    <main className="shell admin-shell">
      <Link className="back" to={`/admin/series/${round.seriesId}`}>
        ← {round.title}
      </Link>
      <header className="submission-heading">
        <p className="eyebrow">Round contributors</p>
        <h1>{round.title}</h1>
        <p>
          Default limit: {round.submissionLimit}. A blank override inherits that
          limit; zero prevents submissions.
        </p>
      </header>
      {!membershipEditable && (
        <p className="muted" role="status">
          Contributor membership is frozen after a round closes so the published
          history remains attributable to the original group.
        </p>
      )}
      <details className="panel round-settings">
        <summary>Round settings</summary>
        {membershipEditable ? (
          <form className="admin-round-form" noValidate onSubmit={submitSettings}>
            <label>Title<input value={selectedTitle} required onChange={(event) => setTitle(event.target.value)} /></label>
            <label>Opens<input type="datetime-local" value={selectedOpensAt} required disabled={!openingEditable} onChange={(event) => setOpensAt(event.target.value)} />{!openingEditable && <span className="field-hint">An open round keeps its original opening time.</span>}</label>
            <label>Closes<input type="datetime-local" min={selectedOpensAt} value={selectedClosesAt} required onChange={(event) => setClosesAt(event.target.value)} /></label>
            <label>Publishes<input type="datetime-local" min={selectedClosesAt} value={selectedPublishAt} required onChange={(event) => setPublishAt(event.target.value)} /></label>
            <label>Submissions per contributor<input type="number" min="0" value={selectedLimit} required onChange={(event) => setSubmissionLimit(event.target.value)} /></label>
            <label>Prompt <span className="field-hint">Optional</span><textarea value={selectedPrompt} maxLength={2000} onChange={(event) => { setPromptEdited(true); setPrompt(event.target.value); }} placeholder="A theme, question, or loose idea for this round." /></label>
            <button className="button" disabled={saveRound.isPending}>{saveRound.isPending ? "Saving…" : "Save round settings"}</button>
          </form>
        ) : <p className="muted">The schedule and default limit are frozen once a round has closed.</p>}
      </details>
      <div className="admin-columns">
        <section className="panel">
          <h2>Add or restore a contributor</h2>
          <label className="member-search-label">
            Find provisioned user
            <input
              value={search}
              placeholder="Name or email"
              onChange={(event) => setSearch(event.target.value)}
            />
          </label>
          <label className="member-search-label">
            Submission limit override
            <input
              type="number"
              min="0"
              value={newLimit}
              placeholder={`Default (${round.submissionLimit})`}
              onChange={(event) => setNewLimit(event.target.value)}
            />
          </label>
          {users.isFetching && <p>Searching users…</p>}
          {users.data?.map((candidate) => (
            <button
              className="user-result"
              type="button"
              key={candidate.id}
              disabled={saveMember.isPending || !membershipEditable}
              onClick={() =>
                saveMember.mutate({ userId: candidate.id, value: newLimit })
              }
            >
              <span>
                {candidate.displayName ?? "Unnamed user"}
                <small>{candidate.email ?? "No email"}</small>
              </span>
              <span>Add</span>
            </button>
          ))}
          {errorMessage(saveMember.error) && (
            <p className="error-message">{errorMessage(saveMember.error)}</p>
          )}
        </section>
        <section className="panel">
          <h2>Current contributors</h2>
          <div className="round-member-list">
            {round.members
              .filter((member) => !member.removedAt)
              .map((member) => {
                const value =
                  overrides[member.id] ??
                  member.submissionLimitOverride?.toString() ??
                  "";
                return (
                  <article key={member.id}>
                    <div>
                      <strong>
                        {member.displayName ?? member.email ?? "Unnamed user"}
                      </strong>
                      <small>{member.email}</small>
                    </div>
                    <label>
                      Override
                      <input
                        type="number"
                        min="0"
                        value={value}
                        disabled={!membershipEditable}
                        placeholder={`Default (${round.submissionLimit})`}
                        onChange={(event) =>
                          setOverrides({
                            ...overrides,
                            [member.id]: event.target.value,
                          })
                        }
                      />
                    </label>
                    <div className="member-actions">
                      <button
                        className="text-button"
                        type="button"
                        disabled={saveMember.isPending || !membershipEditable}
                        onClick={() =>
                          saveMember.mutate({ userId: member.id, value })
                        }
                      >
                        Save
                      </button>
                      <button
                        className="text-button danger"
                        type="button"
                        disabled={removeMember.isPending || !membershipEditable}
                        onClick={() => setMemberToRemove(member)}
                      >
                        Remove
                      </button>
                    </div>
                  </article>
                );
              })}
            {round.members.filter((member) => !member.removedAt).length ===
              0 && <p>No contributors yet.</p>}
          </div>
        </section>
      </div>
      {round.members.some((member) => member.removedAt) && (
        <section className="panel admin-history">
          <h2>Removed contributors</h2>
          <div className="round-member-list">
            {round.members
              .filter((member) => member.removedAt)
              .map((member) => (
                <article key={member.id}>
                  <div>
                    <strong>
                      {member.displayName ?? member.email ?? "Unnamed user"}
                    </strong>
                    <small>Removed {member.removedAt}</small>
                  </div>
                </article>
              ))}
          </div>
        </section>
      )}
      <PublicationPanel round={round} onChanged={invalidate} />
      <ConfirmDialog
        open={Boolean(memberToRemove)}
        title={`Remove ${memberToRemove?.displayName ?? memberToRemove?.email ?? "this contributor"}?`}
        description="They will lose access to this round. Any existing submissions stay in the historical record under their name."
        confirmLabel="Remove contributor"
        isPending={removeMember.isPending}
        onOpenChange={(open) => { if (!open && !removeMember.isPending) setMemberToRemove(null); }}
        onConfirm={() => { if (memberToRemove) removeMember.mutate(memberToRemove.id); }}
      />
    </main>
  );
}
