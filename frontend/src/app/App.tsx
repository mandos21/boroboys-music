import { useQuery } from "@tanstack/react-query";
import { Link, Route, Routes, useParams } from "react-router";

type Session = {
  user: { id: string; email: string | null; displayName: string | null; platformRole: string };
};
type Round = { id: string; title: string; status: string; opensAt: string; closesAt: string; publishAt: string; submissionLimit: number };

async function api<T>(path: string): Promise<T> {
  const response = await fetch(`/api/v1${path}`, { credentials: "include" });
  if (!response.ok) throw new Error(String(response.status));
  return response.json() as Promise<T>;
}

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
  return (
    <main className="shell">
      <header className="topbar">
        <div><p className="eyebrow">Music Rounds</p><h1>Welcome back, {currentUser.displayName ?? "listener"}.</h1></div>
        <span className="role">{currentUser.platformRole}</span>
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
  const round = useQuery({ queryKey: ["round", roundId], queryFn: () => api<Round>(`/rounds/${roundId}`), enabled: Boolean(roundId), retry: false });
  if (round.isLoading) return <main className="shell"><p>Loading round…</p></main>;
  if (round.isError || !round.data) return <main className="shell"><section className="panel"><h1>Round unavailable</h1><p>You may no longer be a contributor in this round.</p><Link to="/">Return to your rounds</Link></section></main>;
  const item = round.data;
  return <main className="shell"><Link className="back" to="/">← Your rounds</Link><section className="panel detail"><span className={`status ${item.status}`}>{item.status}</span><h1>{item.title}</h1><p>Submit up to {item.submissionLimit} tracks during this round.</p><div className="timeline"><div><strong>Opens</strong><span>{formatDate(item.opensAt)}</span></div><div><strong>Closes</strong><span>{formatDate(item.closesAt)}</span></div><div><strong>Published</strong><span>{formatDate(item.publishAt)}</span></div></div><p className="muted">Track search and submission controls appear here when the round is open.</p></section></main>;
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

export function App() {
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/rounds/:roundId" element={<RoundPage />} />
      <Route path="/signed-out" element={<SignedOutPage />} />
    </Routes>
  );
}
