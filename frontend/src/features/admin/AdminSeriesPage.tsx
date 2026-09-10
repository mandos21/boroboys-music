import { useDeferredValue, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router";

import { api, del, patch, put } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import { Button } from "../../components/ui/button";
import { ConfirmDialog } from "../../components/ui/ConfirmDialog";
import { Disclosure } from "../../components/ui/Disclosure";
import { StatePanel } from "../../components/ui/StatePanel";
import { PageSkeleton } from "../../components/ui/PageSkeleton";
import { useToast } from "../../components/ui/ToastProvider";
import { formatDate } from "../../lib/format";
import { HistoricalImportPanel } from "./HistoricalImportPanel";
import { InvitePanel } from "./InvitePanel";
import { RoundScheduleForm } from "./RoundScheduleForm";
import { SuccessorPlanEditor } from "./SuccessorPlanEditor";
import { errorMessage } from "./adminUtils";
import type { Connection, SeriesDetail, User } from "./types";
import "./admin.css";

export function AdminSeriesPage() {
  const { seriesId } = useParams();
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const detail = useQuery({
    queryKey: queryKeys.adminSeriesDetail(seriesId),
    queryFn: () => api<SeriesDetail>(`/admin/series/${seriesId}`),
    enabled: Boolean(seriesId),
    retry: false,
  });
  const members = useQuery({
    queryKey: queryKeys.seriesMembers(seriesId),
    queryFn: () => api<User[]>(`/admin/series/${seriesId}/members`),
    enabled: Boolean(seriesId),
    retry: false,
  });
  const connections = useQuery({
    queryKey: queryKeys.connections(),
    queryFn: () => api<Connection[]>("/connections"),
    retry: false,
  });
  const [memberSearch, setMemberSearch] = useState("");
  const [memberToRemove, setMemberToRemove] = useState<User | null>(null);
  const deferredMemberSearch = useDeferredValue(memberSearch.trim());
  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: queryKeys.adminSeriesDetail(seriesId) });
    queryClient.invalidateQueries({ queryKey: queryKeys.seriesDetail(seriesId) });
    queryClient.invalidateQueries({ queryKey: queryKeys.seriesMembers(seriesId) });
    queryClient.invalidateQueries({ queryKey: queryKeys.series() });
  };

  const matchingUsers = useQuery({
    queryKey: queryKeys.seriesUsers(seriesId, deferredMemberSearch),
    queryFn: () =>
      api<User[]>(
        `/admin/series/${seriesId}/users?query=${encodeURIComponent(deferredMemberSearch)}`,
      ),
    enabled: Boolean(seriesId) && deferredMemberSearch.length >= 2,
  });
  const addMember = useMutation({
    mutationFn: (userId: string) => put(`/admin/series/${seriesId}/members/${userId}`, {}),
    onSuccess: () => {
      setMemberSearch("");
      invalidate();
      showToast({
        title: "Member added",
        description: "They will be included in future rounds for this series.",
      });
    },
    onError: () =>
      showToast({
        title: "Couldn’t add member",
        description: "Try again in a moment.",
        tone: "error",
      }),
  });
  const removeMember = useMutation({
    mutationFn: (userId: string) => del(`/admin/series/${seriesId}/members/${userId}`),
    onSuccess: () => {
      setMemberToRemove(null);
      invalidate();
      showToast({
        title: "Member removed",
        description: "They will not be included in future rounds.",
      });
    },
    onError: () =>
      showToast({
        title: "Couldn’t remove member",
        description: "Try again in a moment.",
        tone: "error",
      }),
  });
  const saveIdentity = useMutation({
    mutationFn: (payload: {
      description: string | null;
      cover_image_url: string | null;
      accent_color: string | null;
    }) => patch(`/admin/series/${seriesId}`, payload),
    onSuccess: () => {
      invalidate();
      showToast({
        title: "Series details saved",
        description: "Its description and look are ready to use.",
      });
    },
    onError: (error) =>
      showToast({
        title: "Couldn’t save series details",
        description: errorMessage(error) ?? "Try again in a moment.",
        tone: "error",
      }),
  });

  if (detail.isLoading)
    return <PageSkeleton label="Loading series workspace" variant="workspace" />;
  if (detail.isError || !detail.data)
    return (
      <main className="shell narrow-page-shell">
        <StatePanel kind="error" title="Series unavailable">
          <Link to="/">Return to your series</Link>
        </StatePanel>
      </main>
    );
  const series = detail.data;
  const currentMembers = members.data ?? [];
  const spotifyAccounts = (connections.data ?? []).filter(
    (account) => account.provider === "spotify" && account.isActive,
  );
  return (
    <main className="shell admin-shell">
      <Link className="back" to={`/series/${series.id}`}>
        ← {series.name}
      </Link>
      <header className="submission-heading">
        <p className="eyebrow">Series management</p>
        <h1>{series.name}</h1>
        <p>
          {series.description ??
            "Set up members, rounds, and the rhythm for this listening series."}
        </p>
      </header>
      <nav className="admin-section-nav" aria-label="Series workspace sections">
        <a href="#rounds">Rounds</a>
        <a href="#members">Members</a>
        <a href="#automation">Automation</a>
        <a href="#history">History</a>
      </nav>
      <section className="series-health" aria-label="Series overview">
        <div>
          <strong>{series.rounds.filter((round) => round.status === "open").length}</strong>
          <span>
            open round
            {series.rounds.filter((round) => round.status === "open").length === 1 ? "" : "s"}
          </span>
        </div>
        <div>
          <strong>{currentMembers.length}</strong>
          <span>series member{currentMembers.length === 1 ? "" : "s"}</span>
        </div>
        <div>
          <strong>{series.autoStartNextRound ? "On" : "Off"}</strong>
          <span>automatic successor</span>
        </div>
      </section>
      <section id="automation" className="admin-workspace-section">
        <div className="workspace-section-heading">
          <div>
            <p className="eyebrow">Future rounds</p>
            <h2>Automation</h2>
          </div>
          <p>Apply a successor plan after each successful publication.</p>
        </div>
        <SuccessorPlanEditor
          key={`${series.id}:${JSON.stringify(series.roundPlan)}:${series.autoStartNextRound}`}
          series={series}
          onSaved={invalidate}
        />
      </section>
      <Disclosure
        className="panel series-identity"
        title="Series details and look"
        description="Describe the series and set an optional cover or accent."
      >
        <form
          onSubmit={(event) => {
            event.preventDefault();
            const fields = new FormData(event.currentTarget);
            saveIdentity.mutate({
              description: String(fields.get("description") || "").trim() || null,
              cover_image_url: String(fields.get("cover") || "").trim() || null,
              accent_color: String(fields.get("accent") || "").trim() || null,
            });
          }}
        >
          <label className="series-description-field">
            Description
            <textarea
              name="description"
              defaultValue={series.description ?? ""}
              maxLength={10_000}
              placeholder="What brings this series together?"
            />
          </label>
          <label>
            Cover image URL
            <input
              name="cover"
              type="url"
              defaultValue={series.coverImageUrl ?? ""}
              placeholder="https://…"
            />
          </label>
          <label>
            Accent color
            <input
              name="accent"
              defaultValue={series.accentColor ?? "#15803d"}
              pattern="#[0-9a-fA-F]{6}"
            />
          </label>
          <Button disabled={saveIdentity.isPending} type="submit" variant="secondary">
            {saveIdentity.isPending ? "Saving…" : "Save series details"}
          </Button>
        </form>
      </Disclosure>
      <div className="admin-columns">
        <section className="panel" id="members">
          <h2>Series members</h2>
          <p className="field-hint">
            Add people individually. Membership applies to rounds you schedule from now on.
          </p>
          <section className="member-picker">
            <label>
              Add a signed-in user
              <input
                value={memberSearch}
                placeholder="Name or email"
                onChange={(event) => setMemberSearch(event.target.value)}
              />
            </label>
            {matchingUsers.isFetching && <p>Searching users…</p>}
            {matchingUsers.data
              ?.filter((candidate) => !currentMembers.some((member) => member.id === candidate.id))
              .map((candidate) => (
                <button
                  type="button"
                  className="user-result"
                  key={candidate.id}
                  disabled={addMember.isPending}
                  onClick={() => addMember.mutate(candidate.id)}
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
          <div className="admin-items member-list">
            {members.isLoading && <p>Loading members…</p>}
            {!members.isLoading && currentMembers.length === 0 && (
              <p>Add people above before scheduling the first round.</p>
            )}
            {currentMembers.map((member) => (
              <article key={member.id}>
                <div>
                  <strong>{member.displayName ?? "Unnamed user"}</strong>
                  <span>{member.email ?? "No email"}</span>
                </div>
                <button
                  type="button"
                  className="text-button danger"
                  onClick={() => setMemberToRemove(member)}
                >
                  Remove
                </button>
              </article>
            ))}
          </div>
        </section>
        <RoundScheduleForm
          series={series}
          members={currentMembers}
          spotifyAccounts={spotifyAccounts}
          onScheduled={invalidate}
        />
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
                  <span className={`status ${round.status}`}>{round.status}</span>
                  <strong>{round.title}</strong>
                  <span>
                    Opens {formatDate(round.opensAt)} · closes {formatDate(round.closesAt)}
                  </span>
                </div>
                <Link to={`/admin/rounds/${round.id}`}>Manage contributors</Link>
              </article>
            ))}
          </div>
        )}
      </section>
      <InvitePanel seriesId={series.id} />
      <HistoricalImportPanel
        seriesId={series.id}
        timezone={series.timezone}
        onImported={invalidate}
      />
      <ConfirmDialog
        open={Boolean(memberToRemove)}
        title="Remove this member?"
        description={
          <>
            They will remain part of already-created rounds, but will not be added to future rounds
            in {series.name}.
          </>
        }
        confirmLabel="Remove member"
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
