import { useDeferredValue, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router";

import { api, post, put } from "../../api/client";
import { StatePanel } from "../../components/ui/StatePanel";
import { useToast } from "../../components/ui/ToastProvider";
import { formatDate } from "../../lib/format";
import { HistoricalImportPanel } from "./HistoricalImportPanel";
import { PolicyEditor } from "./PolicyEditor";
import { SuccessorPlanEditor } from "./SuccessorPlanEditor";
import { errorMessage } from "./adminUtils";
import type { SeriesDetail, User } from "./types";

export function AdminSeriesPage() {
  const { seriesId } = useParams();
  const queryClient = useQueryClient();
  const { showToast } = useToast();
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
  const [policies, setPolicies] = useState<Record<string, unknown>[]>([]);
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
      showToast({ title: "Contributor group added", description: "You can now add provisioned listeners to it." });
    },
    onError: () => showToast({ title: "Couldn’t add group", description: "Try again in a moment.", tone: "error" }),
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
        policy_snapshot: policies.length > 0 ? policies : undefined,
      }),
    onSuccess: () => {
      setRoundTitle("");
      setSelectedGroups([]);
      setPolicies([]);
      invalidate();
      showToast({ title: "Round scheduled", description: "Contributors will see it when its submission window opens." });
    },
    onError: () => showToast({ title: "Couldn’t schedule round", description: "Check the schedule and try again.", tone: "error" }),
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
      showToast({ title: "Member added to group", description: "They can be included in future rounds from this group." });
    },
    onError: () => showToast({ title: "Couldn’t add member", description: "Try again in a moment.", tone: "error" }),
  });
  const groupOptions = useMemo(
    () => detail.data?.groups ?? [],
    [detail.data?.groups],
  );
  if (detail.isLoading) return <main className="shell narrow-page-shell"><StatePanel kind="loading" title="Loading series workspace">Gathering its rounds, groups, and automation settings.</StatePanel></main>;
  if (detail.isError || !detail.data)
    return (
      <main className="shell narrow-page-shell">
        <StatePanel kind="error" title="Series unavailable"><Link to="/admin">Return to managed series</Link></StatePanel>
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
      <nav className="admin-section-nav" aria-label="Series workspace sections">
        <a href="#rounds">Rounds</a><a href="#contributors">Contributors</a><a href="#automation">Automation</a><a href="#history">History</a>
      </nav>
      <section className="series-health" aria-label="Series overview">
        <div><strong>{series.rounds.filter((round) => round.status === "open").length}</strong><span>open round{series.rounds.filter((round) => round.status === "open").length === 1 ? "" : "s"}</span></div>
        <div><strong>{series.groups.length}</strong><span>contributor group{series.groups.length === 1 ? "" : "s"}</span></div>
        <div><strong>{series.autoStartNextRound ? "On" : "Off"}</strong><span>automatic successor</span></div>
      </section>
      <section id="automation" className="admin-workspace-section">
        <div className="workspace-section-heading"><div><p className="eyebrow">Future rounds</p><h2>Automation</h2></div><p>Apply a successor plan after each successful publication.</p></div>
        <SuccessorPlanEditor
          key={`${series.id}:${JSON.stringify(series.roundPlan)}:${series.autoStartNextRound}`}
          series={series}
          onSaved={invalidate}
        />
      </section>
      <div className="admin-columns">
        <section className="panel" id="contributors">
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
        <section className="panel" id="rounds">
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
            <PolicyEditor value={policies} onChange={setPolicies} />
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
      <section className="panel admin-history" id="history">
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
      <HistoricalImportPanel seriesId={series.id} onImported={invalidate} />
    </main>
  );
}
