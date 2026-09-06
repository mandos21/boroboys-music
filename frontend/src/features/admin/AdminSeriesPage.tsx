import { useDeferredValue, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router";

import { api, post, put } from "../../api/client";
import { formatDate } from "../../lib/format";
import { HistoricalImportPanel } from "./HistoricalImportPanel";
import { SuccessorPlanEditor } from "./SuccessorPlanEditor";
import { errorMessage } from "./adminUtils";
import type { SeriesDetail, User } from "./types";

export function AdminSeriesPage() {
  const { seriesId } = useParams();
  const queryClient = useQueryClient();
  const detail = useQuery({
    queryKey: ["admin-series", seriesId],
    queryFn: () => api<SeriesDetail>(`/admin/series/${seriesId}`),
    enabled: Boolean(seriesId),
    retry: false,
  });
  const [groupName, setGroupName] = useState("");
  const [roundTitle, setRoundTitle] = useState("");
  const [opensAt, setOpensAt] = useState("");
  const [closesAt, setClosesAt] = useState("");
  const [publishAt, setPublishAt] = useState("");
  const [submissionLimit, setSubmissionLimit] = useState("1");
  const [selectedGroups, setSelectedGroups] = useState<string[]>([]);
  const [policies, setPolicies] = useState("[]");
  const [memberSearch, setMemberSearch] = useState("");
  const [targetGroupId, setTargetGroupId] = useState("");
  const deferredMemberSearch = useDeferredValue(memberSearch.trim());
  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ["admin-series", seriesId] });
  const createGroup = useMutation({
    mutationFn: () =>
      post(`/admin/series/${seriesId}/groups`, { name: groupName }),
    onSuccess: () => {
      setGroupName("");
      invalidate();
    },
  });
  const createRound = useMutation({
    mutationFn: () =>
      post("/admin/rounds", {
        series_id: seriesId,
        title: roundTitle,
        timezone: detail.data?.timezone,
        opens_at: new Date(opensAt).toISOString(),
        closes_at: new Date(closesAt).toISOString(),
        publish_at: new Date(publishAt).toISOString(),
        submission_limit: Number(submissionLimit),
        contributor_group_ids: selectedGroups,
        policy_snapshot: JSON.parse(policies),
      }),
    onSuccess: () => {
      setRoundTitle("");
      setSelectedGroups([]);
      invalidate();
    },
  });
  const matchingUsers = useQuery({
    queryKey: ["series-users", seriesId, deferredMemberSearch],
    queryFn: () =>
      api<User[]>(
        `/admin/series/${seriesId}/users?query=${encodeURIComponent(deferredMemberSearch)}`,
      ),
    enabled: Boolean(seriesId) && deferredMemberSearch.length >= 2,
  });
  const addMember = useMutation({
    mutationFn: ({ groupId, userId }: { groupId: string; userId: string }) =>
      put(`/admin/groups/${groupId}/members/${userId}`, {}),
    onSuccess: () => {
      setMemberSearch("");
      invalidate();
    },
  });
  const groupOptions = useMemo(
    () => detail.data?.groups ?? [],
    [detail.data?.groups],
  );
  if (detail.isLoading)
    return (
      <main className="shell">
        <p>Loading series administration…</p>
      </main>
    );
  if (detail.isError || !detail.data)
    return (
      <main className="shell">
        <section className="panel">
          <h1>Series unavailable</h1>
          <Link to="/admin">Return to series</Link>
        </section>
      </main>
    );
  const series = detail.data;
  return (
    <main className="shell admin-shell">
      <Link className="back" to="/admin">
        ← Managed series
      </Link>
      <header className="submission-heading">
        <p className="eyebrow">{series.timezone}</p>
        <h1>{series.name}</h1>
        <p>
          {series.description ??
            "Configure contributor groups and schedule distinct rounds for this series."}
        </p>
      </header>
      <SuccessorPlanEditor
        key={`${series.id}:${JSON.stringify(series.roundPlan)}:${series.autoStartNextRound}`}
        series={series}
        onSaved={invalidate}
      />
      <HistoricalImportPanel seriesId={series.id} onImported={invalidate} />
      <div className="admin-columns">
        <section className="panel">
          <h2>Contributor groups</h2>
          <form
            className="inline-form"
            onSubmit={(event) => {
              event.preventDefault();
              createGroup.mutate();
            }}
          >
            <label>
              Name
              <input
                value={groupName}
                required
                maxLength={200}
                onChange={(event) => setGroupName(event.target.value)}
              />
            </label>
            <button className="button" disabled={createGroup.isPending}>
              Add group
            </button>
          </form>
          {errorMessage(createGroup.error) && (
            <p className="error-message">{errorMessage(createGroup.error)}</p>
          )}
          {series.groups.length > 0 && (
            <section className="member-picker">
              <label>
                Add a provisioned user
                <input
                  value={memberSearch}
                  placeholder="Name or email"
                  onChange={(event) => setMemberSearch(event.target.value)}
                />
              </label>
              <label>
                To group
                <select
                  value={targetGroupId}
                  onChange={(event) => setTargetGroupId(event.target.value)}
                >
                  <option value="">Choose a group</option>
                  {series.groups.map((group) => (
                    <option key={group.id} value={group.id}>
                      {group.name}
                    </option>
                  ))}
                </select>
              </label>
              {matchingUsers.isFetching && <p>Searching users…</p>}
              {matchingUsers.data?.map((candidate) => (
                <button
                  type="button"
                  className="user-result"
                  key={candidate.id}
                  disabled={!targetGroupId || addMember.isPending}
                  onClick={() =>
                    addMember.mutate({
                      groupId: targetGroupId,
                      userId: candidate.id,
                    })
                  }
                >
                  <span>
                    {candidate.displayName ?? "Unnamed user"}
                    <small>{candidate.email ?? "No email"}</small>
                  </span>
                  <span>Add</span>
                </button>
              ))}
              {errorMessage(addMember.error) && (
                <p className="error-message">{errorMessage(addMember.error)}</p>
              )}
            </section>
          )}
          <div className="admin-items">
            {series.groups.length === 0 && (
              <p>
                Create a reusable group, then add members who have signed in at
                least once.
              </p>
            )}
            {series.groups.map((group) => (
              <article key={group.id}>
                <div>
                  <strong>{group.name}</strong>
                  <span>{group.memberCount} members</span>
                  {group.members.map((member) => (
                    <span className="group-member" key={member.id}>
                      {member.displayName ?? member.email ?? "Unnamed user"}
                    </span>
                  ))}
                </div>
              </article>
            ))}
          </div>
        </section>
        <section className="panel">
          <h2>Schedule a round</h2>
          <form
            className="admin-round-form"
            onSubmit={(event) => {
              event.preventDefault();
              createRound.mutate();
            }}
          >
            <label>
              Title
              <input
                value={roundTitle}
                required
                maxLength={200}
                onChange={(event) => setRoundTitle(event.target.value)}
              />
            </label>
            <label>
              Opens
              <input
                type="datetime-local"
                value={opensAt}
                required
                onChange={(event) => setOpensAt(event.target.value)}
              />
            </label>
            <label>
              Closes
              <input
                type="datetime-local"
                value={closesAt}
                required
                onChange={(event) => setClosesAt(event.target.value)}
              />
            </label>
            <label>
              Publish after close
              <input
                type="datetime-local"
                value={publishAt}
                required
                onChange={(event) => setPublishAt(event.target.value)}
              />
            </label>
            <label>
              Submissions per contributor
              <input
                type="number"
                min="0"
                value={submissionLimit}
                required
                onChange={(event) => setSubmissionLimit(event.target.value)}
              />
            </label>
            <label>
              Contributor groups
              <select
                multiple
                value={selectedGroups}
                onChange={(event) =>
                  setSelectedGroups(
                    [...event.target.selectedOptions].map(
                      (option) => option.value,
                    ),
                  )
                }
              >
                {groupOptions.map((group) => (
                  <option key={group.id} value={group.id}>
                    {group.name} ({group.memberCount})
                  </option>
                ))}
              </select>
            </label>
            <label>
              Policy snapshot (JSON)
              <textarea
                value={policies}
                onChange={(event) => setPolicies(event.target.value)}
              />
            </label>
            <button className="button" disabled={createRound.isPending}>
              {createRound.isPending ? "Scheduling…" : "Schedule round"}
            </button>
            {errorMessage(createRound.error) && (
              <p className="error-message" role="alert">
                {errorMessage(createRound.error)}
              </p>
            )}
          </form>
        </section>
      </div>
      <section className="panel admin-history">
        <h2>Rounds</h2>
        {series.rounds.length === 0 ? (
          <p>No rounds are scheduled yet.</p>
        ) : (
          <div className="admin-items">
            {series.rounds.map((round) => (
              <article key={round.id}>
                <div>
                  <span className={`status ${round.status}`}>
                    {round.status}
                  </span>
                  <strong>{round.title}</strong>
                  <span>
                    Opens {formatDate(round.opensAt)} · closes{" "}
                    {formatDate(round.closesAt)}
                  </span>
                </div>
                <Link to={`/admin/rounds/${round.id}`}>
                  Manage contributors
                </Link>
              </article>
            ))}
          </div>
        )}
      </section>
    </main>
  );
}
