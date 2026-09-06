import { FormEvent, useDeferredValue, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router";

import { ApiError, api, del, patch, post, put } from "../../api/client";
import "./admin.css";

type Session = { user: { platformRole: string } };
type Series = {
  id: string;
  name: string;
  slug: string;
  description: string | null;
  timezone: string;
  defaultPolicies: Record<string, unknown>[];
  roundPlan: Record<string, unknown> | null;
  autoStartNextRound: boolean;
  isArchived: boolean;
};
type User = { id: string; displayName: string | null; email: string | null };
type Group = { id: string; name: string; description: string | null; memberCount: number; members: User[] };
type Round = { id: string; title: string; status: string; opensAt: string; closesAt: string; publishAt: string; submissionLimit: number };
type SeriesDetail = Series & { groups: Group[]; rounds: Round[] };
type RoundMember = User & { submissionLimitOverride: number | null; removedAt: string | null };
type AdminRound = Round & { seriesId: string; timezone: string; policySnapshot: Record<string, unknown>[]; members: RoundMember[] };
type Connection = { id: string; provider: string; displayName: string | null; isActive: boolean };
type Publication = {
  id: string;
  state: string;
  isImported: boolean;
  spotifyPlaylistId: string | null;
  attemptCount: number;
  lastError: string | null;
  publishedAt: string | null;
  unpublishedAt: string | null;
  events: Array<{ id: string; action: string; createdAt: string }>;
};

function formatDate(value: string): string {
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

function errorMessage(error: unknown): string | null {
  return error instanceof ApiError ? error.message : null;
}

export function AdminIndexPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const session = useQuery({ queryKey: ["session"], queryFn: () => api<Session>("/auth/session"), retry: false });
  const series = useQuery({ queryKey: ["admin-series"], queryFn: () => api<Series[]>("/admin/series") });
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [timezone, setTimezone] = useState(Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC");
  const [planKind, setPlanKind] = useState<"none" | "rolling" | "calendar">("none");
  const [rollingHours, setRollingHours] = useState("");
  const [calendarDay, setCalendarDay] = useState("1");
  const [calendarDuration, setCalendarDuration] = useState("7");
  const [nextLimit, setNextLimit] = useState("");
  const [autoStart, setAutoStart] = useState(true);
  const create = useMutation({
    mutationFn: () => post<{ id: string }>("/admin/series", {
      name,
      slug,
      timezone,
      default_policies: [],
      auto_start_next_round: planKind === "none" ? false : autoStart,
      round_plan: planKind === "rolling" ? {
        kind: "rolling",
        duration_hours: Number(rollingHours),
        submission_limit: nextLimit ? Number(nextLimit) : null,
      } : planKind === "calendar" ? {
        kind: "calendar",
        open_day: Number(calendarDay),
        duration_days: Number(calendarDuration),
        submission_limit: nextLimit ? Number(nextLimit) : null,
      } : null,
    }),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ["admin-series"] });
      navigate(`/admin/series/${result.id}`);
    },
  });
  const isPlatformAdmin = session.data?.user.platformRole === "admin";

  function submit(event: FormEvent) {
    event.preventDefault();
    create.mutate();
  }

  return (
    <main className="shell admin-shell">
      <Link className="back" to="/">← Your rounds</Link>
      <header className="submission-heading"><p className="eyebrow">Administration</p><h1>Series and rounds</h1><p>A series owns its history, reusable contributor groups, policy defaults, and an optional automatic successor plan.</p></header>
      {isPlatformAdmin && <section className="panel admin-create"><h2>Create a series</h2><form onSubmit={submit}><label>Name<input value={name} required maxLength={200} onChange={(event) => { setName(event.target.value); if (!slug) setSlug(event.target.value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "")); }} /></label><label>Slug<input value={slug} required pattern="[a-z0-9]+(?:-[a-z0-9]+)*" maxLength={100} onChange={(event) => setSlug(event.target.value)} /></label><label>Timezone<input value={timezone} required onChange={(event) => setTimezone(event.target.value)} /></label><fieldset className="rolling-plan"><legend>Automatic next round</legend><label>Timeline<select value={planKind} onChange={(event) => setPlanKind(event.target.value as "none" | "rolling" | "calendar")}><option value="none">None — schedule rounds manually</option><option value="rolling">Rolling — starts after publication</option><option value="calendar">Calendar — monthly schedule</option></select></label>{planKind === "rolling" && <label>Round duration in hours<input type="number" required min="1" max="8760" value={rollingHours} onChange={(event) => setRollingHours(event.target.value)} /></label>}{planKind === "calendar" && <><label>Open on day of month<input type="number" required min="1" max="28" value={calendarDay} onChange={(event) => setCalendarDay(event.target.value)} /></label><label>Submission window in days<input type="number" required min="1" max="366" value={calendarDuration} onChange={(event) => setCalendarDuration(event.target.value)} /></label></>}<label>Next-round submission limit (optional)<input type="number" min="0" value={nextLimit} disabled={planKind === "none"} onChange={(event) => setNextLimit(event.target.value)} /></label><label className="check-label"><input type="checkbox" checked={autoStart} disabled={planKind === "none"} onChange={(event) => setAutoStart(event.target.checked)} />Start the successor when this round is published</label></fieldset><button className="button" disabled={create.isPending}>{create.isPending ? "Creating…" : "Create series"}</button>{errorMessage(create.error) && <p className="error-message" role="alert">{errorMessage(create.error)}</p>}</form></section>}
      <section className="admin-list"><h2>Your managed series</h2>{series.isLoading && <p>Loading series…</p>}{series.isError && <p className="error-message" role="alert">{errorMessage(series.error) ?? "Series could not be loaded."}</p>}{series.data?.length === 0 && <p>You do not administer a series yet.</p>}{series.data?.map((item) => <Link className="panel admin-series-card" key={item.id} to={`/admin/series/${item.id}`}><div><span className="role">{item.timezone}</span><h3>{item.name}</h3><p>{item.description ?? "No description yet."}</p></div><span aria-hidden="true">→</span></Link>)}</section>
    </main>
  );
}

function SuccessorPlanEditor({ series, onSaved }: { series: Series; onSaved: () => void }) {
  const initialKind = series.roundPlan?.kind === "rolling" || series.roundPlan?.kind === "calendar"
    ? series.roundPlan.kind
    : "none";
  const [kind, setKind] = useState<"none" | "rolling" | "calendar">(initialKind);
  const [rollingHours, setRollingHours] = useState(String(series.roundPlan?.duration_hours ?? ""));
  const [calendarDay, setCalendarDay] = useState(String(series.roundPlan?.open_day ?? 1));
  const [calendarDuration, setCalendarDuration] = useState(String(series.roundPlan?.duration_days ?? 7));
  const [limit, setLimit] = useState(String(series.roundPlan?.submission_limit ?? ""));
  const [autoStart, setAutoStart] = useState(series.autoStartNextRound);
  const save = useMutation({
    mutationFn: () => patch(`/admin/series/${series.id}`, {
      auto_start_next_round: kind === "none" ? false : autoStart,
      round_plan: kind === "rolling" ? {
        kind: "rolling", duration_hours: Number(rollingHours), submission_limit: limit ? Number(limit) : null,
      } : kind === "calendar" ? {
        kind: "calendar", open_day: Number(calendarDay), duration_days: Number(calendarDuration), submission_limit: limit ? Number(limit) : null,
      } : null,
    }),
    onSuccess: onSaved,
  });
  return <section className="panel"><h2>Automatic next round</h2><p>Changing this affects only successors created after a successful publication.</p><form className="admin-round-form" onSubmit={(event) => { event.preventDefault(); save.mutate(); }}><label>Timeline<select value={kind} onChange={(event) => setKind(event.target.value as "none" | "rolling" | "calendar")}><option value="none">None — schedule rounds manually</option><option value="rolling">Rolling — starts after publication</option><option value="calendar">Calendar — monthly schedule</option></select></label>{kind === "rolling" && <label>Round duration in hours<input type="number" required min="1" max="8760" value={rollingHours} onChange={(event) => setRollingHours(event.target.value)} /></label>}{kind === "calendar" && <><label>Open on day of month<input type="number" required min="1" max="28" value={calendarDay} onChange={(event) => setCalendarDay(event.target.value)} /></label><label>Submission window in days<input type="number" required min="1" max="366" value={calendarDuration} onChange={(event) => setCalendarDuration(event.target.value)} /></label></>}<label>Successor submission limit (optional)<input type="number" min="0" disabled={kind === "none"} value={limit} onChange={(event) => setLimit(event.target.value)} /></label><label className="check-label"><input type="checkbox" checked={autoStart} disabled={kind === "none"} onChange={(event) => setAutoStart(event.target.checked)} />Start the successor automatically</label><button className="button" disabled={save.isPending}>{save.isPending ? "Saving…" : "Save plan"}</button>{errorMessage(save.error) && <p className="error-message" role="alert">{errorMessage(save.error)}</p>}</form></section>;
}

function HistoricalImportPanel({ seriesId, onImported }: { seriesId: string; onImported: () => void }) {
  const [publisherId, setPublisherId] = useState("");
  const [playlistId, setPlaylistId] = useState("");
  const [title, setTitle] = useState("");
  const [opensAt, setOpensAt] = useState("");
  const [closesAt, setClosesAt] = useState("");
  const [publishedAt, setPublishedAt] = useState("");
  const connections = useQuery({ queryKey: ["connections"], queryFn: () => api<Connection[]>("/connections"), retry: false });
  const importPlaylist = useMutation({
    mutationFn: () => post<{ roundId: string }>(`/admin/series/${seriesId}/import-spotify-playlist`, {
      publisher_account_id: publisherId,
      spotify_playlist_id: playlistId,
      title: title.trim() || null,
      opens_at: new Date(opensAt).toISOString(),
      closes_at: new Date(closesAt).toISOString(),
      published_at: new Date(publishedAt).toISOString(),
    }),
    onSuccess: () => { setPlaylistId(""); setTitle(""); onImported(); },
  });
  const accounts = (connections.data ?? []).filter((account) => account.provider === "spotify" && account.isActive);
  return <details className="panel historical-import"><summary>Import a historical Spotify playlist</summary><p>Imports preserve the remote track order and create an immutable published round. Imported playlists are never retired remotely.</p>{accounts.length === 0 ? <p><Link to="/settings/connections">Link a Spotify account</Link> before importing.</p> : <form className="admin-round-form" onSubmit={(event) => { event.preventDefault(); importPlaylist.mutate(); }}><label>Spotify publisher<select required value={publisherId} onChange={(event) => setPublisherId(event.target.value)}><option value="">Choose an account</option>{accounts.map((account) => <option key={account.id} value={account.id}>{account.displayName ?? "Spotify account"}</option>)}</select></label><label>Playlist ID<input required value={playlistId} placeholder="Spotify playlist ID" maxLength={128} onChange={(event) => setPlaylistId(event.target.value)} /></label><label>Round title (optional)<input value={title} maxLength={200} onChange={(event) => setTitle(event.target.value)} /></label><label>Opened<input type="datetime-local" required value={opensAt} onChange={(event) => setOpensAt(event.target.value)} /></label><label>Closed<input type="datetime-local" required value={closesAt} onChange={(event) => setClosesAt(event.target.value)} /></label><label>Published<input type="datetime-local" required value={publishedAt} onChange={(event) => setPublishedAt(event.target.value)} /></label><button className="button" disabled={importPlaylist.isPending}>{importPlaylist.isPending ? "Importing…" : "Import playlist"}</button>{errorMessage(importPlaylist.error) && <p className="error-message" role="alert">{errorMessage(importPlaylist.error)}</p>}</form>}</details>;
}

export function AdminSeriesPage() {
  const { seriesId } = useParams();
  const queryClient = useQueryClient();
  const detail = useQuery({ queryKey: ["admin-series", seriesId], queryFn: () => api<SeriesDetail>(`/admin/series/${seriesId}`), enabled: Boolean(seriesId), retry: false });
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
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["admin-series", seriesId] });
  const createGroup = useMutation({ mutationFn: () => post(`/admin/series/${seriesId}/groups`, { name: groupName }), onSuccess: () => { setGroupName(""); invalidate(); } });
  const createRound = useMutation({
    mutationFn: () => post("/admin/rounds", {
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
    onSuccess: () => { setRoundTitle(""); setSelectedGroups([]); invalidate(); },
  });
  const matchingUsers = useQuery({
    queryKey: ["series-users", seriesId, deferredMemberSearch],
    queryFn: () => api<User[]>(`/admin/series/${seriesId}/users?query=${encodeURIComponent(deferredMemberSearch)}`),
    enabled: Boolean(seriesId) && deferredMemberSearch.length >= 2,
  });
  const addMember = useMutation({
    mutationFn: ({ groupId, userId }: { groupId: string; userId: string }) =>
      put(`/admin/groups/${groupId}/members/${userId}`, {}),
    onSuccess: () => { setMemberSearch(""); invalidate(); },
  });
  const groupOptions = useMemo(() => detail.data?.groups ?? [], [detail.data?.groups]);
  if (detail.isLoading) return <main className="shell"><p>Loading series administration…</p></main>;
  if (detail.isError || !detail.data) return <main className="shell"><section className="panel"><h1>Series unavailable</h1><Link to="/admin">Return to series</Link></section></main>;
  const series = detail.data;
  return (
    <main className="shell admin-shell">
      <Link className="back" to="/admin">← Managed series</Link>
      <header className="submission-heading"><p className="eyebrow">{series.timezone}</p><h1>{series.name}</h1><p>{series.description ?? "Configure contributor groups and schedule distinct rounds for this series."}</p></header>
      <SuccessorPlanEditor key={`${series.id}:${JSON.stringify(series.roundPlan)}:${series.autoStartNextRound}`} series={series} onSaved={invalidate} />
      <HistoricalImportPanel seriesId={series.id} onImported={invalidate} />
      <div className="admin-columns">
        <section className="panel"><h2>Contributor groups</h2><form className="inline-form" onSubmit={(event) => { event.preventDefault(); createGroup.mutate(); }}><label>Name<input value={groupName} required maxLength={200} onChange={(event) => setGroupName(event.target.value)} /></label><button className="button" disabled={createGroup.isPending}>Add group</button></form>{errorMessage(createGroup.error) && <p className="error-message">{errorMessage(createGroup.error)}</p>}{series.groups.length > 0 && <section className="member-picker"><label>Add a provisioned user<input value={memberSearch} placeholder="Name or email" onChange={(event) => setMemberSearch(event.target.value)} /></label><label>To group<select value={targetGroupId} onChange={(event) => setTargetGroupId(event.target.value)}><option value="">Choose a group</option>{series.groups.map((group) => <option key={group.id} value={group.id}>{group.name}</option>)}</select></label>{matchingUsers.isFetching && <p>Searching users…</p>}{matchingUsers.data?.map((candidate) => <button type="button" className="user-result" key={candidate.id} disabled={!targetGroupId || addMember.isPending} onClick={() => addMember.mutate({ groupId: targetGroupId, userId: candidate.id })}><span>{candidate.displayName ?? "Unnamed user"}<small>{candidate.email ?? "No email"}</small></span><span>Add</span></button>)}{errorMessage(addMember.error) && <p className="error-message">{errorMessage(addMember.error)}</p>}</section>}<div className="admin-items">{series.groups.length === 0 && <p>Create a reusable group, then add members who have signed in at least once.</p>}{series.groups.map((group) => <article key={group.id}><div><strong>{group.name}</strong><span>{group.memberCount} members</span>{group.members.map((member) => <span className="group-member" key={member.id}>{member.displayName ?? member.email ?? "Unnamed user"}</span>)}</div></article>)}</div></section>
        <section className="panel"><h2>Schedule a round</h2><form className="admin-round-form" onSubmit={(event) => { event.preventDefault(); createRound.mutate(); }}><label>Title<input value={roundTitle} required maxLength={200} onChange={(event) => setRoundTitle(event.target.value)} /></label><label>Opens<input type="datetime-local" value={opensAt} required onChange={(event) => setOpensAt(event.target.value)} /></label><label>Closes<input type="datetime-local" value={closesAt} required onChange={(event) => setClosesAt(event.target.value)} /></label><label>Publish after close<input type="datetime-local" value={publishAt} required onChange={(event) => setPublishAt(event.target.value)} /></label><label>Submissions per contributor<input type="number" min="0" value={submissionLimit} required onChange={(event) => setSubmissionLimit(event.target.value)} /></label><label>Contributor groups<select multiple value={selectedGroups} onChange={(event) => setSelectedGroups([...event.target.selectedOptions].map((option) => option.value))}>{groupOptions.map((group) => <option key={group.id} value={group.id}>{group.name} ({group.memberCount})</option>)}</select></label><label>Policy snapshot (JSON)<textarea value={policies} onChange={(event) => setPolicies(event.target.value)} /></label><button className="button" disabled={createRound.isPending}>{createRound.isPending ? "Scheduling…" : "Schedule round"}</button>{errorMessage(createRound.error) && <p className="error-message" role="alert">{errorMessage(createRound.error)}</p>}</form></section>
      </div>
      <section className="panel admin-history"><h2>Rounds</h2>{series.rounds.length === 0 ? <p>No rounds are scheduled yet.</p> : <div className="admin-items">{series.rounds.map((round) => <article key={round.id}><div><span className={`status ${round.status}`}>{round.status}</span><strong>{round.title}</strong><span>Opens {formatDate(round.opensAt)} · closes {formatDate(round.closesAt)}</span></div><Link to={`/admin/rounds/${round.id}`}>Manage contributors</Link></article>)}</div>}</section>
    </main>
  );
}

export function AdminRoundPage() {
  const { roundId } = useParams();
  const queryClient = useQueryClient();
  const detail = useQuery({ queryKey: ["admin-round", roundId], queryFn: () => api<AdminRound>(`/admin/rounds/${roundId}`), enabled: Boolean(roundId), retry: false });
  const [search, setSearch] = useState("");
  const [newLimit, setNewLimit] = useState("");
  const [overrides, setOverrides] = useState<Record<string, string>>({});
  const deferredSearch = useDeferredValue(search.trim());
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["admin-round", roundId] });
  const users = useQuery({
    queryKey: ["round-users", detail.data?.seriesId, deferredSearch],
    queryFn: () => api<User[]>(`/admin/series/${detail.data?.seriesId}/users?query=${encodeURIComponent(deferredSearch)}`),
    enabled: Boolean(detail.data?.seriesId) && deferredSearch.length >= 2,
  });
  const saveMember = useMutation({
    mutationFn: ({ userId, value }: { userId: string; value: string }) => put(`/admin/rounds/${roundId}/members/${userId}`, { submission_limit_override: value === "" ? null : Number(value) }),
    onSuccess: invalidate,
  });
  const removeMember = useMutation({ mutationFn: (userId: string) => del(`/admin/rounds/${roundId}/members/${userId}`), onSuccess: invalidate });
  if (detail.isLoading) return <main className="shell"><p>Loading round contributors…</p></main>;
  if (detail.isError || !detail.data) return <main className="shell"><section className="panel"><h1>Round unavailable</h1><Link to="/admin">Return to series</Link></section></main>;
  const round = detail.data;
  return (
    <main className="shell admin-shell">
      <Link className="back" to={`/admin/series/${round.seriesId}`}>← {round.title}</Link>
      <header className="submission-heading"><p className="eyebrow">Round contributors</p><h1>{round.title}</h1><p>Default limit: {round.submissionLimit}. A blank override inherits that limit; zero prevents submissions.</p></header>
      <div className="admin-columns">
        <section className="panel"><h2>Add or restore a contributor</h2><label className="member-search-label">Find provisioned user<input value={search} placeholder="Name or email" onChange={(event) => setSearch(event.target.value)} /></label><label className="member-search-label">Submission limit override<input type="number" min="0" value={newLimit} placeholder={`Default (${round.submissionLimit})`} onChange={(event) => setNewLimit(event.target.value)} /></label>{users.isFetching && <p>Searching users…</p>}{users.data?.map((candidate) => <button className="user-result" type="button" key={candidate.id} disabled={saveMember.isPending} onClick={() => saveMember.mutate({ userId: candidate.id, value: newLimit })}><span>{candidate.displayName ?? "Unnamed user"}<small>{candidate.email ?? "No email"}</small></span><span>Add</span></button>)}{errorMessage(saveMember.error) && <p className="error-message">{errorMessage(saveMember.error)}</p>}</section>
        <section className="panel"><h2>Current contributors</h2><div className="round-member-list">{round.members.filter((member) => !member.removedAt).map((member) => { const value = overrides[member.id] ?? (member.submissionLimitOverride?.toString() ?? ""); return <article key={member.id}><div><strong>{member.displayName ?? member.email ?? "Unnamed user"}</strong><small>{member.email}</small></div><label>Override<input type="number" min="0" value={value} placeholder={`Default (${round.submissionLimit})`} onChange={(event) => setOverrides({ ...overrides, [member.id]: event.target.value })} /></label><div className="member-actions"><button className="text-button" type="button" disabled={saveMember.isPending} onClick={() => saveMember.mutate({ userId: member.id, value })}>Save</button><button className="text-button danger" type="button" disabled={removeMember.isPending} onClick={() => removeMember.mutate(member.id)}>Remove</button></div></article>; })}{round.members.filter((member) => !member.removedAt).length === 0 && <p>No contributors yet.</p>}</div></section>
      </div>
      {round.members.some((member) => member.removedAt) && <section className="panel admin-history"><h2>Removed contributors</h2><div className="round-member-list">{round.members.filter((member) => member.removedAt).map((member) => <article key={member.id}><div><strong>{member.displayName ?? member.email ?? "Unnamed user"}</strong><small>Removed {member.removedAt}</small></div></article>)}</div></section>}
      <PublicationPanel round={round} onChanged={invalidate} />
    </main>
  );
}

function PublicationPanel({ round, onChanged }: { round: AdminRound; onChanged: () => void }) {
  const queryClient = useQueryClient();
  const publication = useQuery({ queryKey: ["publication", round.id], queryFn: () => api<Publication | null>(`/admin/rounds/${round.id}/publication`), retry: false });
  const connections = useQuery({ queryKey: ["connections"], queryFn: () => api<Connection[]>("/connections"), retry: false });
  const [publisherId, setPublisherId] = useState("");
  const invalidate = () => { queryClient.invalidateQueries({ queryKey: ["publication", round.id] }); onChanged(); };
  const publish = useMutation({ mutationFn: () => post(`/admin/rounds/${round.id}/publish`, { publisher_account_id: publisherId }), onSuccess: invalidate });
  const unpublish = useMutation({ mutationFn: () => post(`/admin/rounds/${round.id}/unpublish`, {}), onSuccess: invalidate });
  const retry = useMutation({ mutationFn: (publicationId: string) => post(`/admin/publications/${publicationId}/retry`, {}), onSuccess: invalidate });
  const spotifyAccounts = (connections.data ?? []).filter((account) => account.provider === "spotify" && account.isActive);
  const current = publication.data;
  const error = errorMessage(publish.error) ?? errorMessage(unpublish.error) ?? errorMessage(retry.error);
  return <section className="panel publication-panel"><h2>Publication</h2>{publication.isLoading && <p>Loading publication status…</p>}{publication.isError && <p className="error-message" role="alert">Publication status could not be loaded.</p>}{!current && round.status === "closed" && <><p>Choose one of your linked Spotify accounts to publish this closed round.</p>{spotifyAccounts.length === 0 ? <p><Link to="/settings/connections">Link a Spotify account</Link> before publishing.</p> : <><label>Spotify publisher<select value={publisherId} onChange={(event) => setPublisherId(event.target.value)}><option value="">Choose an account</option>{spotifyAccounts.map((account) => <option value={account.id} key={account.id}>{account.displayName ?? "Spotify account"}</option>)}</select></label><button className="button" type="button" disabled={!publisherId || publish.isPending} onClick={() => publish.mutate()}>{publish.isPending ? "Queueing…" : "Publish to Spotify"}</button></>}</>}{!current && round.status !== "closed" && <p>This round can be published after it has closed.</p>}{current && <><p><span className={`status ${current.state}`}>{current.state}</span> {current.isImported ? "Historical import" : `${current.attemptCount} publish attempt${current.attemptCount === 1 ? "" : "s"}`}</p>{current.spotifyPlaylistId && <p><a href={`https://open.spotify.com/playlist/${current.spotifyPlaylistId}`} target="_blank" rel="noreferrer">Open Spotify playlist</a></p>}{current.lastError && <p className="error-message" role="alert">{current.lastError}</p>}{["publishing", "unpublishing"].includes(current.state) && <p aria-live="polite">The worker is processing this publication. Refresh this page for the latest status.</p>}{current.state === "failed" && <button type="button" className="button" disabled={retry.isPending} onClick={() => retry.mutate(current.id)}>{retry.isPending ? "Retrying…" : "Retry publication"}</button>}{round.status === "published" && !current.isImported && <button type="button" className="danger-button" disabled={unpublish.isPending} onClick={() => unpublish.mutate()}>{unpublish.isPending ? "Queueing reversal…" : "Unpublish latest round"}</button>}{round.status === "published" && current.isImported && <p className="muted">Historical imports are retained and cannot be unpublished remotely.</p>}{current.events.length > 0 && <section className="publication-events"><h3>Audit history</h3><ul>{current.events.map((event) => <li key={event.id}><strong>{event.action}</strong><span>{formatDate(event.createdAt)}</span></li>)}</ul></section>}</>}{error && <p className="error-message" role="alert">{error}</p>}</section>;
}
