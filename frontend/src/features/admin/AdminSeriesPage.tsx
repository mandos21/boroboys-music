import { useDeferredValue, useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router";

import { api, del, patch, post, put } from "../../api/client";
import { ConfirmDialog } from "../../components/ui/ConfirmDialog";
import { StatePanel } from "../../components/ui/StatePanel";
import { useToast } from "../../components/ui/ToastProvider";
import { formatDate } from "../../lib/format";
import { endOfWallMonth, monthTitle, nextWallDay, toZonedInput, zonedInputToIso } from "../../lib/time";
import { HistoricalImportPanel } from "./HistoricalImportPanel";
import { InvitePanel } from "./InvitePanel";
import { PolicyEditor } from "./PolicyEditor";
import { SuccessorPlanEditor } from "./SuccessorPlanEditor";
import { errorMessage } from "./adminUtils";
import type { Connection, SeriesDetail, User } from "./types";

function suggestedOpening(rounds: SeriesDetail["rounds"] | undefined, timezone: string) {
  const now = new Date();
  now.setSeconds(0, 0);
  if (!rounds?.length) return toZonedInput(now, timezone);
  const mostRecent = [...rounds].sort(
    (first, second) => Date.parse(second.publishAt) - Date.parse(first.publishAt),
  )[0];
  const publishedAt = mostRecent ? new Date(mostRecent.publishAt) : now;
  return toZonedInput(new Date(Math.max(now.getTime(), publishedAt.getTime())), timezone);
}

export function AdminSeriesPage() {
  const { seriesId } = useParams();
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const detail = useQuery({ queryKey: ["admin-series", seriesId], queryFn: () => api<SeriesDetail>(`/admin/series/${seriesId}`), enabled: Boolean(seriesId), retry: false });
  const members = useQuery({ queryKey: ["series-members", seriesId], queryFn: () => api<User[]>(`/admin/series/${seriesId}/members`), enabled: Boolean(seriesId), retry: false });
  const connections = useQuery({ queryKey: ["connections"], queryFn: () => api<Connection[]>("/connections"), retry: false });
  const [roundTitle, setRoundTitle] = useState("");
  const [opensAt, setOpensAt] = useState("");
  const [closesAt, setClosesAt] = useState("");
  const [publishAt, setPublishAt] = useState("");
  const [submissionLimit, setSubmissionLimit] = useState("3");
  const [prompt, setPrompt] = useState("");
  const [titleEdited, setTitleEdited] = useState(false);
  const [closeEdited, setCloseEdited] = useState(false);
  const [publishEdited, setPublishEdited] = useState(false);
  const [policies, setPolicies] = useState<Record<string, unknown>[]>([]);
  const [memberSearch, setMemberSearch] = useState("");
  const [publisher, setPublisher] = useState("");
  const [memberToRemove, setMemberToRemove] = useState<User | null>(null);
  const deferredMemberSearch = useDeferredValue(memberSearch.trim());
  const seriesTimezone = detail.data?.timezone ?? "UTC";
  const defaultOpensAt = suggestedOpening(detail.data?.rounds, seriesTimezone);
  const selectedOpensAt = opensAt || defaultOpensAt;
  const monthly = detail.data?.roundPlan?.kind === "calendar" && detail.data.roundPlan?.full_month === true;
  const selectedClosesAt = closesAt || (monthly ? endOfWallMonth(selectedOpensAt) : "");
  const selectedPublishAt = publishAt || (monthly ? nextWallDay(selectedClosesAt) : "");
  const selectedTitle = roundTitle || (monthly && !titleEdited ? monthTitle(selectedOpensAt) : "");
  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["admin-series", seriesId] });
    queryClient.invalidateQueries({ queryKey: ["series", seriesId] });
    queryClient.invalidateQueries({ queryKey: ["series-members", seriesId] });
    queryClient.invalidateQueries({ queryKey: ["series"] });
  };

  const createRound = useMutation({
    mutationFn: () => post("/admin/rounds", {
      series_id: seriesId, title: selectedTitle, timezone: detail.data?.timezone,
      opens_at: zonedInputToIso(selectedOpensAt, seriesTimezone), closes_at: zonedInputToIso(selectedClosesAt, seriesTimezone), publish_at: zonedInputToIso(selectedPublishAt, seriesTimezone),
      submission_limit: Number(submissionLimit), contributor_user_ids: (members.data ?? []).map((member) => member.id),
      policy_snapshot: policies.length > 0 ? policies : undefined,
      prompt: prompt.trim() || null,
      publisher_account_id: publisher || null,
    }),
    onSuccess: () => { setRoundTitle(""); setTitleEdited(false); setOpensAt(""); setClosesAt(""); setCloseEdited(false); setPublishAt(""); setPublishEdited(false); setPrompt(""); setPolicies([]); invalidate(); showToast({ title: "Round scheduled", description: "Every current series member will be included." }); },
    onError: (error) => showToast({ title: "Couldn’t schedule round", description: errorMessage(error) ?? "Check the schedule and try again.", tone: "error" }),
  });
  const matchingUsers = useQuery({ queryKey: ["series-users", seriesId, deferredMemberSearch], queryFn: () => api<User[]>(`/admin/series/${seriesId}/users?query=${encodeURIComponent(deferredMemberSearch)}`), enabled: Boolean(seriesId) && deferredMemberSearch.length >= 2 });
  const addMember = useMutation({
    mutationFn: (userId: string) => put(`/admin/series/${seriesId}/members/${userId}`, {}),
    onSuccess: () => { setMemberSearch(""); invalidate(); showToast({ title: "Member added", description: "They will be included in future rounds for this series." }); },
    onError: () => showToast({ title: "Couldn’t add member", description: "Try again in a moment.", tone: "error" }),
  });
  const removeMember = useMutation({
    mutationFn: (userId: string) => del(`/admin/series/${seriesId}/members/${userId}`),
    onSuccess: () => { setMemberToRemove(null); invalidate(); showToast({ title: "Member removed", description: "They will not be included in future rounds." }); },
    onError: () => showToast({ title: "Couldn’t remove member", description: "Try again in a moment.", tone: "error" }),
  });
  const saveIdentity = useMutation({
    mutationFn: (payload: { description: string | null; cover_image_url: string | null; accent_color: string | null }) => patch(`/admin/series/${seriesId}`, payload),
    onSuccess: () => { invalidate(); showToast({ title: "Series details saved", description: "Its description and look are ready to use." }); },
    onError: (error) => showToast({ title: "Couldn’t save series details", description: errorMessage(error) ?? "Try again in a moment.", tone: "error" }),
  });

  if (detail.isLoading) return <main className="shell narrow-page-shell"><StatePanel kind="loading" title="Loading series workspace">Gathering its rounds, members, and automation settings.</StatePanel></main>;
  if (detail.isError || !detail.data) return <main className="shell narrow-page-shell"><StatePanel kind="error" title="Series unavailable"><Link to="/">Return to your series</Link></StatePanel></main>;
  const series = detail.data;
  const currentMembers = members.data ?? [];
  const spotifyAccounts = (connections.data ?? []).filter(
    (account) => account.provider === "spotify" && account.isActive,
  );
  function submitRound(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedTitle.trim()) return showToast({ title: "Add a round title", tone: "error" });
    const openingIso = zonedInputToIso(selectedOpensAt, seriesTimezone);
    const closingIso = zonedInputToIso(selectedClosesAt, seriesTimezone);
    const publishingIso = zonedInputToIso(selectedPublishAt, seriesTimezone);
    if (!openingIso || !closingIso || !publishingIso) return showToast({ title: "Use valid series times", description: "One of these times does not exist in the series timezone, usually because of daylight saving time.", tone: "error" });
    if (new Date(selectedOpensAt) >= new Date(selectedClosesAt)) return showToast({ title: "Closing must follow opening", tone: "error" });
    if (new Date(selectedClosesAt) > new Date(selectedPublishAt)) return showToast({ title: "Publish after the round closes", tone: "error" });
    createRound.mutate();
  }
  return (
    <main className="shell admin-shell">
      <Link className="back" to={`/series/${series.id}`}>← {series.name}</Link>
      <header className="submission-heading"><p className="eyebrow">Series management · {series.timezone}</p><h1>{series.name}</h1><p>{series.description ?? "Set up members, rounds, and the rhythm for this listening series."}</p></header>
      <nav className="admin-section-nav" aria-label="Series workspace sections"><a href="#rounds">Rounds</a><a href="#members">Members</a><a href="#automation">Automation</a><a href="#history">History</a></nav>
      <section className="series-health" aria-label="Series overview"><div><strong>{series.rounds.filter((round) => round.status === "open").length}</strong><span>open round{series.rounds.filter((round) => round.status === "open").length === 1 ? "" : "s"}</span></div><div><strong>{currentMembers.length}</strong><span>series member{currentMembers.length === 1 ? "" : "s"}</span></div><div><strong>{series.autoStartNextRound ? "On" : "Off"}</strong><span>automatic successor</span></div></section>
      <section id="automation" className="admin-workspace-section"><div className="workspace-section-heading"><div><p className="eyebrow">Future rounds</p><h2>Automation</h2></div><p>Apply a successor plan after each successful publication.</p></div><SuccessorPlanEditor key={`${series.id}:${JSON.stringify(series.roundPlan)}:${series.autoStartNextRound}`} series={series} onSaved={invalidate} /></section>
      <details className="panel series-identity"><summary>Series details and look</summary><form onSubmit={(event) => { event.preventDefault(); const fields = new FormData(event.currentTarget); saveIdentity.mutate({ description: String(fields.get("description") || "").trim() || null, cover_image_url: String(fields.get("cover") || "").trim() || null, accent_color: String(fields.get("accent") || "").trim() || null }); }}><label className="series-description-field">Description<textarea name="description" defaultValue={series.description ?? ""} maxLength={10_000} placeholder="What brings this series together?" /></label><label>Cover image URL<input name="cover" type="url" defaultValue={series.coverImageUrl ?? ""} placeholder="https://…" /></label><label>Accent color<input name="accent" defaultValue={series.accentColor ?? "#15803d"} pattern="#[0-9a-fA-F]{6}" /></label><button className="button button-secondary" disabled={saveIdentity.isPending}>{saveIdentity.isPending ? "Saving…" : "Save series details"}</button></form></details>
      <div className="admin-columns">
        <section className="panel" id="members"><h2>Series members</h2><p className="field-hint">Add people individually. Membership applies to rounds you schedule from now on.</p>
          <section className="member-picker"><label>Add a signed-in user<input value={memberSearch} placeholder="Name or email" onChange={(event) => setMemberSearch(event.target.value)} /></label>
            {matchingUsers.isFetching && <p>Searching users…</p>}
            {matchingUsers.data?.filter((candidate) => !currentMembers.some((member) => member.id === candidate.id)).map((candidate) => <button type="button" className="user-result" key={candidate.id} disabled={addMember.isPending} onClick={() => addMember.mutate(candidate.id)}><span>{candidate.displayName ?? "Unnamed user"}<small>{candidate.email ?? "No email"}</small></span><span>Add</span></button>)}
            {errorMessage(addMember.error) && <p className="error-message">{errorMessage(addMember.error)}</p>}
          </section>
          <div className="admin-items member-list">{members.isLoading && <p>Loading members…</p>}{!members.isLoading && currentMembers.length === 0 && <p>Add people above before scheduling the first round.</p>}{currentMembers.map((member) => <article key={member.id}><div><strong>{member.displayName ?? "Unnamed user"}</strong><span>{member.email ?? "No email"}</span></div><button type="button" className="text-button danger" onClick={() => setMemberToRemove(member)}>Remove</button></article>)}</div>
        </section>
        <section className="panel" id="rounds"><h2>Schedule a round</h2><form className="admin-round-form" noValidate onSubmit={submitRound}>
          <label>Title<input value={selectedTitle} required maxLength={200} onChange={(event) => { setTitleEdited(true); setRoundTitle(event.target.value); }} /></label>
          <label>Opens<input type="datetime-local" value={selectedOpensAt} required onChange={(event) => { setOpensAt(event.target.value); if (monthly && !closeEdited) setClosesAt(""); if (monthly && !publishEdited) setPublishAt(""); if (monthly && !titleEdited) setRoundTitle(""); }} /><span className="field-hint">Times use {seriesTimezone}. Defaults to now, unless the latest round publishes later.</span></label>
          <label>Closes<input type="datetime-local" min={selectedOpensAt || undefined} value={selectedClosesAt} required onChange={(event) => { setCloseEdited(true); setClosesAt(event.target.value); if (monthly && !publishEdited) setPublishAt(""); }} /></label>
          <label>Publishes<input type="datetime-local" min={selectedClosesAt || undefined} value={selectedPublishAt} required onChange={(event) => { setPublishEdited(true); setPublishAt(event.target.value); }} /></label>
          <label>Submissions per contributor<input type="number" min="0" value={submissionLimit} required onChange={(event) => setSubmissionLimit(event.target.value)} /></label>
          <label>Prompt <span className="field-hint">Optional</span><textarea value={prompt} maxLength={2000} onChange={(event) => setPrompt(event.target.value)} placeholder="A theme, question, or loose idea for this round." /></label>
          <p className="field-hint">{currentMembers.length ? `${currentMembers.length} current series member${currentMembers.length === 1 ? "" : "s"} will be included.` : "Add members before scheduling this round."}</p>
          <label>Publishing account <span className="field-hint">Optional</span>
            <select value={publisher} onChange={(event) => setPublisher(event.target.value)}>
              <option value="">Release this round by hand</option>
              {spotifyAccounts.map((account) => <option key={account.id} value={account.id}>{account.displayName ?? "Spotify account"}</option>)}
            </select>
            <span className="field-hint">{publisher ? "This round releases itself at its publish time." : "Without an account, somebody has to publish the round once it closes."}{spotifyAccounts.length === 0 ? " Link a Spotify account on your profile to enable this." : ""}</span>
          </label>
          <PolicyEditor value={policies} onChange={setPolicies} />
          <button className="button" disabled={createRound.isPending || currentMembers.length === 0}>{createRound.isPending ? "Scheduling…" : "Schedule round"}</button>
          {errorMessage(createRound.error) && <p className="error-message" role="alert">{errorMessage(createRound.error)}</p>}
        </form></section>
      </div>
      <section className="panel admin-history" id="history"><h2>Rounds</h2>{series.rounds.length === 0 ? <p>No rounds are scheduled yet.</p> : <div className="admin-items">{series.rounds.map((round) => <article key={round.id}><div><span className={`status ${round.status}`}>{round.status}</span><strong>{round.title}</strong><span>Opens {formatDate(round.opensAt)} · closes {formatDate(round.closesAt)}</span></div><Link to={`/admin/rounds/${round.id}`}>Manage contributors</Link></article>)}</div>}</section>
      <InvitePanel seriesId={series.id} />
      <HistoricalImportPanel seriesId={series.id} timezone={series.timezone} onImported={invalidate} />
      <ConfirmDialog open={Boolean(memberToRemove)} title="Remove this member?" description={<>They will remain part of already-created rounds, but will not be added to future rounds in {series.name}.</>} confirmLabel="Remove member" isPending={removeMember.isPending} onOpenChange={(open) => { if (!open && !removeMember.isPending) setMemberToRemove(null); }} onConfirm={() => { if (memberToRemove) removeMember.mutate(memberToRemove.id); }} />
    </main>
  );
}
