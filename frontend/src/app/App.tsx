import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, Route, Routes, useParams } from "react-router";

import { api, logout, patch, post } from "../api/client";
import { AdminIndexPage, AdminRoundPage, AdminSeriesPage } from "../features/admin/AdminPages";
import { ConnectionsPage } from "../features/connections/ConnectionsPage";
import { SubmissionPage } from "../features/submissions/SubmissionPage";

type Session = {
  user: { id: string; email: string | null; displayName: string | null; platformRole: string };
};
type Round = { id: string; seriesId?: string; title: string; status: string; opensAt: string; closesAt: string; publishAt: string; submissionLimit: number };
type SeriesHistory = {
  id: string;
  name: string;
  description: string | null;
  timezone: string;
  rounds: Array<{ id: string; title: string; status: string; opensAt: string; closesAt: string; publishAt: string }>;
};
type Submission = {
  id: string;
  status: "accepted" | "withdrawn";
  note: string | null;
  createdAt: string;
  isMine: boolean;
  contributor: { id: string; displayName: string | null };
  track: { name: string; artist: string; album: string | null };
};

function formatDate(value: string) {
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

function HomePage() {
  const session = useQuery({ queryKey: ["session"], queryFn: () => api<Session>("/auth/session"), retry: false });
  const rounds = useQuery({ queryKey: ["rounds"], queryFn: () => api<Round[]>("/rounds"), enabled: session.isSuccess });
  if (session.isLoading) return <main className="shell"><p>Loading Music Rounds…</p></main>;
  if (session.isError) return <LandingPage />;
  if (!session.data) return <LandingPage />;
  const currentUser = session.data.user;
  const signOut = async () => {
    try {
      window.location.assign(await logout());
    } catch {
      window.location.assign("/signed-out");
    }
  };
  return (
    <main className="shell">
      <header className="topbar">
        <div><p className="eyebrow">Music Rounds</p><h1>Welcome back, {currentUser.displayName ?? "listener"}.</h1></div>
        <div className="topbar-actions"><Link to="/admin">Manage series</Link><Link to="/settings/connections">Connections</Link><button className="link-button" type="button" onClick={signOut}>Sign out</button><span className="role">{currentUser.platformRole}</span></div>
      </header>
      <section className="panel">
        <h2>Your rounds</h2>
        {rounds.isLoading && <p>Finding your rounds…</p>}
        {rounds.isError && <p role="alert">Your rounds could not be loaded. Please refresh.</p>}
        {rounds.data?.length === 0 && <p>You are not a contributor in any rounds yet.</p>}
        <div className="round-grid">
          {rounds.data?.map((round) => <article className="round-card" key={round.id}>
            <div><span className={`status ${round.status}`}>{round.status}</span><h3>{round.title}</h3></div>
            <dl><div><dt>Closes</dt><dd>{formatDate(round.closesAt)}</dd></div><div><dt>Submissions</dt><dd>Up to {round.submissionLimit}</dd></div></dl>
            <Link to={`/rounds/${round.id}`}>Open round <span aria-hidden="true">→</span></Link>
          </article>)}
        </div>
      </section>
    </main>
  );
}

function LandingPage() {
  return <main className="shell"><section className="hero"><p className="eyebrow">Music Rounds</p><h1>Curated listening, on your group&apos;s schedule.</h1><p>Submit tracks, discover your group&apos;s listening history, and publish each finished round to Spotify.</p><a className="button" href="/api/v1/auth/login">Sign in</a></section></main>;
}

function RoundPage() {
  const { roundId } = useParams();
  const queryClient = useQueryClient();
  const round = useQuery({ queryKey: ["round", roundId], queryFn: () => api<Round>(`/rounds/${roundId}`), enabled: Boolean(roundId), retry: false });
  const submissions = useQuery({ queryKey: ["round-submissions", roundId], queryFn: () => api<Submission[]>(`/rounds/${roundId}/submissions`), enabled: Boolean(roundId) && round.isSuccess, retry: false });
  const withdraw = useMutation({
    mutationFn: (submissionId: string) => post<void>(`/rounds/submissions/${submissionId}/withdraw`, undefined),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["round-submissions", roundId] }),
  });
  const updateNote = useMutation({
    mutationFn: ({ submissionId, note }: { submissionId: string; note: string | null }) => patch<void>(`/rounds/submissions/${submissionId}`, { note }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["round-submissions", roundId] }),
  });
  if (round.isLoading) return <main className="shell"><p>Loading round…</p></main>;
  if (round.isError || !round.data) return <main className="shell"><section className="panel"><h1>Round unavailable</h1><p>You may no longer be a contributor in this round.</p><Link to="/">Return to your rounds</Link></section></main>;
  const item = round.data;
  return <main className="shell"><Link className="back" to="/">← Your rounds</Link><section className="panel detail"><span className={`status ${item.status}`}>{item.status}</span><h1>{item.title}</h1><p>Submit up to {item.submissionLimit} tracks during this round.</p><div className="timeline"><div><strong>Opens</strong><span>{formatDate(item.opensAt)}</span></div><div><strong>Closes</strong><span>{formatDate(item.closesAt)}</span></div><div><strong>Published</strong><span>{formatDate(item.publishAt)}</span></div></div>{item.status === "open" ? <Link className="button" to={`/rounds/${item.id}/submit`}>Choose a track</Link> : <p className="muted">Submissions are currently closed.</p>}{item.seriesId && <Link className="history-link" to={`/series/${item.seriesId}`}>View series history</Link>}</section><RoundSubmissions roundId={item.id} submissions={submissions} roundIsOpen={item.status === "open"} onWithdraw={(id) => withdraw.mutate(id)} onSaveNote={(id, note) => updateNote.mutate({ submissionId: id, note })} /></main>;
}

function RoundSubmissions({ roundId, submissions, roundIsOpen, onWithdraw, onSaveNote }: { roundId: string; submissions: ReturnType<typeof useQuery<Submission[]>>; roundIsOpen: boolean; onWithdraw: (id: string) => void; onSaveNote: (id: string, note: string | null) => void }) {
  if (submissions.isLoading) return <section className="panel"><p>Loading submissions…</p></section>;
  if (submissions.isError) return <section className="panel"><p role="alert">Submissions could not be loaded.</p></section>;
  const entries = submissions.data ?? [];
  return <section className="panel submission-history"><h2>Submissions</h2>{entries.length === 0 ? <p>No tracks have been submitted yet.</p> : <ul>{entries.map((entry) => <li key={entry.id} className={entry.status === "withdrawn" ? "withdrawn" : ""}><div><strong>{entry.track.name}</strong><span>{entry.track.artist}{entry.track.album ? ` · ${entry.track.album}` : ""}</span><small>{entry.isMine ? "Your submission" : entry.contributor.displayName ?? "A contributor"}</small></div>{entry.note && <p>{entry.note}</p>}{entry.isMine && entry.status === "accepted" && roundIsOpen && <details><summary>Manage your submission</summary><form onSubmit={(event) => { event.preventDefault(); const form = new FormData(event.currentTarget); onSaveNote(entry.id, String(form.get("note") || "").trim() || null); }}><label htmlFor={`note-${entry.id}`}>Note</label><textarea id={`note-${entry.id}`} name="note" defaultValue={entry.note ?? ""} maxLength={4000} /><div className="inline-actions"><button type="submit">Save note</button><Link to={`/rounds/${roundId}/submit?replace=${entry.id}`}>Replace track</Link><button type="button" className="danger" onClick={() => onWithdraw(entry.id)}>Withdraw</button></div></form></details>}</li>)}</ul>}</section>;
}

function SignedOutPage() {
  return (
    <main className="shell">
      <section className="panel">
        <h1>You have been signed out.</h1>
        <Link to="/">Return to Music Rounds</Link>
      </section>
    </main>
  );
}

function SeriesPage() {
  const { seriesId } = useParams();
  const series = useQuery({ queryKey: ["series", seriesId], queryFn: () => api<SeriesHistory>(`/series/${seriesId}`), enabled: Boolean(seriesId), retry: false });
  if (series.isLoading) return <main className="shell"><p>Loading series history…</p></main>;
  if (series.isError || !series.data) return <main className="shell"><section className="panel"><h1>Series unavailable</h1><p>You do not have access to this series.</p><Link to="/">Return to your rounds</Link></section></main>;
  const item = series.data;
  return <main className="shell"><Link className="back" to="/">← Your rounds</Link><section className="panel detail"><p className="eyebrow">Series history</p><h1>{item.name}</h1>{item.description && <p>{item.description}</p>}<p className="muted">Times shown in {item.timezone}.</p><div className="series-round-list">{item.rounds.map((round) => <article key={round.id}><span className={`status ${round.status}`}>{round.status}</span><div><h2>{round.title}</h2><p>Opened {formatDate(round.opensAt)} · Published {formatDate(round.publishAt)}</p></div><Link to={`/rounds/${round.id}`}>View round</Link></article>)}</div></section></main>;
}

export function App() {
  return (
    <>
      <a className="skip-link" href="#main-content">Skip to main content</a>
      <div id="main-content" tabIndex={-1}>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/rounds/:roundId" element={<RoundPage />} />
          <Route path="/rounds/:roundId/submit" element={<SubmissionPage />} />
          <Route path="/series/:seriesId" element={<SeriesPage />} />
          <Route path="/settings/connections" element={<ConnectionsPage />} />
          <Route path="/admin" element={<AdminIndexPage />} />
          <Route path="/admin/series/:seriesId" element={<AdminSeriesPage />} />
          <Route path="/admin/rounds/:roundId" element={<AdminRoundPage />} />
          <Route path="/signed-out" element={<SignedOutPage />} />
        </Routes>
      </div>
    </>
  );
}
