import { useDeferredValue, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, del, put } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import { ConfirmDialog } from "../../components/ui/ConfirmDialog";
import { useToast } from "../../components/ui/ToastProvider";
import { InvitePanel } from "./InvitePanel";
import { errorMessage } from "./adminUtils";
import type { SeriesDetail, User } from "./types";

export function SeriesMembersTab({ series, active }: { series: SeriesDetail; active: boolean }) {
  const seriesId = series.id;
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const members = useQuery({
    queryKey: queryKeys.seriesMembers(seriesId),
    queryFn: () => api<User[]>(`/admin/series/${seriesId}/members`),
    enabled: active,
  });
  const currentMembers = members.data ?? [];
  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: queryKeys.seriesMembers(seriesId) });
  const [memberSearch, setMemberSearch] = useState("");
  const [memberToRemove, setMemberToRemove] = useState<User | null>(null);
  const deferredMemberSearch = useDeferredValue(memberSearch.trim());
  const matchingUsers = useQuery({
    queryKey: queryKeys.seriesUsers(seriesId, deferredMemberSearch),
    queryFn: () =>
      api<User[]>(
        `/admin/series/${seriesId}/users?query=${encodeURIComponent(deferredMemberSearch)}`,
      ),
    enabled: active && deferredMemberSearch.length >= 2,
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

  return (
    <>
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
          {members.isError && (
            <p role="alert">
              Couldn’t load members.{" "}
              <button className="text-button" onClick={() => members.refetch()}>
                Try again
              </button>
            </p>
          )}
          {!members.isLoading && !members.isError && currentMembers.length === 0 && (
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

      <InvitePanel seriesId={seriesId} />
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
    </>
  );
}
