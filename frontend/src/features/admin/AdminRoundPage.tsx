import { useDeferredValue, useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router";

import { api, del, patch, put } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import { ConfirmDialog } from "../../components/ui/ConfirmDialog";
import { useToast } from "../../components/ui/ToastProvider";
import { formatDate } from "../../lib/format";
import { toZonedInput, zonedInputToIso } from "../../lib/time";
import { PublicationPanel } from "./PublicationPanel";
import { errorMessage } from "./adminUtils";
import type { AdminRound, Connection, User } from "./types";

export function AdminRoundPage() {
  const { roundId } = useParams();
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const detail = useQuery({
    queryKey: queryKeys.adminRound(roundId),
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
  const [publisher, setPublisher] = useState<string | null>(null);
  const deferredSearch = useDeferredValue(search.trim());
  const connections = useQuery({
    queryKey: queryKeys.connections(),
    queryFn: () => api<Connection[]>("/connections"),
    retry: false,
  });
  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: queryKeys.adminRound(roundId) });
  const users = useQuery({
    queryKey: queryKeys.roundUsers(detail.data?.seriesId, deferredSearch),
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
      showToast({
        title: "Contributor updated",
        description: "Their round access and submission limit are saved.",
      });
    },
    onError: () =>
      showToast({
        title: "Couldn’t update contributor",
        description: "Try again in a moment.",
        tone: "error",
      }),
  });
  const removeMember = useMutation({
    mutationFn: (userId: string) => del(`/admin/rounds/${roundId}/members/${userId}`),
    onSuccess: () => {
      invalidate();
      setMemberToRemove(null);
      showToast({
        title: "Contributor removed",
        description: "Their existing submissions remain attributable in this round.",
      });
    },
    onError: () =>
      showToast({
        title: "Couldn’t remove contributor",
        description: "Try again in a moment.",
        tone: "error",
      }),
  });
  const saveRound = useMutation({
    mutationFn: (payload: Record<string, unknown>) => patch(`/admin/rounds/${roundId}`, payload),
    onSuccess: () => {
      invalidate();
      showToast({
        title: "Round settings saved",
        description: "The schedule and submission limit are updated.",
      });
    },
    onError: (error) =>
      showToast({
        title: "Couldn’t save round settings",
        description: errorMessage(error) ?? "Try again in a moment.",
        tone: "error",
      }),
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
  const membershipEditable = ["draft", "scheduled", "open"].includes(round.status);
  const openingEditable = ["draft", "scheduled"].includes(round.status);
  const selectedTitle = title || round.title;
  const selectedOpensAt = opensAt || toZonedInput(round.opensAt, round.timezone);
  const selectedClosesAt = closesAt || toZonedInput(round.closesAt, round.timezone);
  const selectedPublishAt = publishAt || toZonedInput(round.publishAt, round.timezone);
  const selectedLimit = submissionLimit || String(round.submissionLimit);
  const selectedPrompt = promptEdited ? prompt : (round.prompt ?? "");
  const selectedPublisher = publisher ?? round.publisherAccountId ?? "";
  const spotifyAccounts = (connections.data ?? []).filter(
    (account) => account.provider === "spotify" && account.isActive,
  );
  function submitSettings(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedTitle.trim()) return showToast({ title: "Add a round title", tone: "error" });
    const openingIso = zonedInputToIso(selectedOpensAt, round.timezone);
    const closingIso = zonedInputToIso(selectedClosesAt, round.timezone);
    const publishingIso = zonedInputToIso(selectedPublishAt, round.timezone);
    if (!openingIso || !closingIso || !publishingIso)
      return showToast({
        title: "Use valid round times",
        description:
          "One of these times does not exist in the round timezone, usually because of daylight saving time.",
        tone: "error",
      });
    if (new Date(openingIso) >= new Date(closingIso))
      return showToast({ title: "Closing must follow opening", tone: "error" });
    if (new Date(closingIso) > new Date(publishingIso))
      return showToast({ title: "Publish after the round closes", tone: "error" });
    saveRound.mutate({
      title: selectedTitle,
      ...(openingEditable ? { opens_at: openingIso } : {}),
      closes_at: closingIso,
      publish_at: publishingIso,
      submission_limit: Number(selectedLimit),
      prompt: selectedPrompt.trim() || null,
      publisher_account_id: selectedPublisher || null,
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
          Default limit: {round.submissionLimit}. A blank override inherits that limit; zero
          prevents submissions.
        </p>
      </header>
      {!membershipEditable && (
        <p className="muted" role="status">
          Contributor membership is frozen after a round closes so the published history remains
          attributable to the original group.
        </p>
      )}
      <details className="panel round-settings">
        <summary>Round settings</summary>
        {membershipEditable ? (
          <form className="admin-round-form" noValidate onSubmit={submitSettings}>
            <label>
              Title
              <input
                value={selectedTitle}
                required
                onChange={(event) => setTitle(event.target.value)}
              />
            </label>
            <label>
              Opens
              <input
                type="datetime-local"
                value={selectedOpensAt}
                required
                disabled={!openingEditable}
                onChange={(event) => setOpensAt(event.target.value)}
              />
              <span className="field-hint">
                Times use {round.timezone}.
                {!openingEditable ? " An open round keeps its original opening time." : ""}
              </span>
            </label>
            <label>
              Closes
              <input
                type="datetime-local"
                min={selectedOpensAt}
                value={selectedClosesAt}
                required
                onChange={(event) => setClosesAt(event.target.value)}
              />
            </label>
            <label>
              Publishes
              <input
                type="datetime-local"
                min={selectedClosesAt}
                value={selectedPublishAt}
                required
                onChange={(event) => setPublishAt(event.target.value)}
              />
            </label>
            <label>
              Submissions per contributor
              <input
                type="number"
                min="0"
                value={selectedLimit}
                required
                onChange={(event) => setSubmissionLimit(event.target.value)}
              />
            </label>
            <label>
              Prompt <span className="field-hint">Optional</span>
              <textarea
                value={selectedPrompt}
                maxLength={2000}
                onChange={(event) => {
                  setPromptEdited(true);
                  setPrompt(event.target.value);
                }}
                placeholder="A theme, question, or loose idea for this round."
              />
            </label>
            <label>
              Publishing account <span className="field-hint">Optional</span>
              <select
                value={selectedPublisher}
                onChange={(event) => setPublisher(event.target.value)}
              >
                <option value="">Release this round by hand</option>
                {spotifyAccounts.map((account) => (
                  <option key={account.id} value={account.id}>
                    {account.displayName ?? "Spotify account"}
                  </option>
                ))}
              </select>
              <span className="field-hint">
                {selectedPublisher
                  ? `This round releases itself at its publish time, through this Spotify account.`
                  : "Without an account, the round stays closed until somebody publishes it."}
                {spotifyAccounts.length === 0
                  ? " Link a Spotify account on your profile to enable this."
                  : ""}
              </span>
            </label>
            <button className="button" disabled={saveRound.isPending}>
              {saveRound.isPending ? "Saving…" : "Save round settings"}
            </button>
          </form>
        ) : (
          <p className="muted">
            The schedule and default limit are frozen once a round has closed.
          </p>
        )}
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
              onClick={() => saveMember.mutate({ userId: candidate.id, value: newLimit })}
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
                  overrides[member.id] ?? member.submissionLimitOverride?.toString() ?? "";
                return (
                  <article key={member.id}>
                    <div>
                      <strong>{member.displayName ?? member.email ?? "Unnamed user"}</strong>
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
                        onClick={() => saveMember.mutate({ userId: member.id, value })}
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
            {round.members.filter((member) => !member.removedAt).length === 0 && (
              <p>No contributors yet.</p>
            )}
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
                    <strong>{member.displayName ?? member.email ?? "Unnamed user"}</strong>
                    <small>
                      Removed {member.removedAt ? formatDate(member.removedAt) : "earlier"}
                    </small>
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
        onOpenChange={(open) => {
          if (!open && !removeMember.isPending) setMemberToRemove(null);
        }}
        onConfirm={() => {
          if (memberToRemove) removeMember.mutate(memberToRemove.id);
        }}
      />
    </main>
  );
}
