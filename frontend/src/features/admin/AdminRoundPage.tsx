import { useDeferredValue, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router";

import { api, del, put } from "../../api/client";
import { PublicationPanel } from "./PublicationPanel";
import { errorMessage } from "./adminUtils";
import type { AdminRound, User } from "./types";

export function AdminRoundPage() {
  const { roundId } = useParams();
  const queryClient = useQueryClient();
  const detail = useQuery({
    queryKey: ["admin-round", roundId],
    queryFn: () => api<AdminRound>(`/admin/rounds/${roundId}`),
    enabled: Boolean(roundId),
    retry: false,
  });
  const [search, setSearch] = useState("");
  const [newLimit, setNewLimit] = useState("");
  const [overrides, setOverrides] = useState<Record<string, string>>({});
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
    onSuccess: invalidate,
  });
  const removeMember = useMutation({
    mutationFn: (userId: string) =>
      del(`/admin/rounds/${roundId}/members/${userId}`),
    onSuccess: invalidate,
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
                        onClick={() => removeMember.mutate(member.id)}
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
    </main>
  );
}
