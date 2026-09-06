import { useQuery } from "@tanstack/react-query";
import { Link, Route, Routes } from "react-router";

import { api, logout } from "../api/client";
import {
  AdminIndexPage,
  AdminRoundPage,
  AdminSeriesPage,
} from "../features/admin/AdminPages";
import { ConnectionsPage } from "../features/connections/ConnectionsPage";
import { RoundPage, SeriesPage } from "../features/rounds/RoundPages";
import { SubmissionPage } from "../features/submissions/SubmissionPage";
import { formatDate } from "../lib/format";

type Session = {
  user: {
    id: string;
    email: string | null;
    displayName: string | null;
    platformRole: string;
  };
};

type Round = {
  id: string;
  title: string;
  status: string;
  closesAt: string;
  submissionLimit: number;
};

function HomePage() {
  const session = useQuery({
    queryKey: ["session"],
    queryFn: () => api<Session>("/auth/session"),
    retry: false,
  });
  const rounds = useQuery({
    queryKey: ["rounds"],
    queryFn: () => api<Round[]>("/rounds"),
    enabled: session.isSuccess,
  });
  if (session.isLoading)
    return (
      <main className="shell">
        <p>Loading Music Rounds…</p>
      </main>
    );
  if (session.isError || !session.data) return <LandingPage />;
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
        <div>
          <p className="eyebrow">Music Rounds</p>
          <h1>Welcome back, {currentUser.displayName ?? "listener"}.</h1>
        </div>
        <div className="topbar-actions">
          <Link to="/admin">Manage series</Link>
          <Link to="/settings/connections">Connections</Link>
          <button className="link-button" type="button" onClick={signOut}>
            Sign out
          </button>
          <span className="role">{currentUser.platformRole}</span>
        </div>
      </header>
      <section className="panel">
        <h2>Your rounds</h2>
        {rounds.isLoading && <p>Finding your rounds…</p>}
        {rounds.isError && (
          <p role="alert">Your rounds could not be loaded. Please refresh.</p>
        )}
        {rounds.data?.length === 0 && (
          <p>You are not a contributor in any rounds yet.</p>
        )}
        <div className="round-grid">
          {rounds.data?.map((round) => (
            <article className="round-card" key={round.id}>
              <div>
                <span className={`status ${round.status}`}>{round.status}</span>
                <h3>{round.title}</h3>
              </div>
              <dl>
                <div>
                  <dt>Closes</dt>
                  <dd>{formatDate(round.closesAt)}</dd>
                </div>
                <div>
                  <dt>Submissions</dt>
                  <dd>Up to {round.submissionLimit}</dd>
                </div>
              </dl>
              <Link to={`/rounds/${round.id}`}>
                Open round <span aria-hidden="true">→</span>
              </Link>
            </article>
          ))}
        </div>
      </section>
    </main>
  );
}

function LandingPage() {
  return (
    <main className="shell">
      <section className="hero">
        <p className="eyebrow">Music Rounds</p>
        <h1>Curated listening, on your group&apos;s schedule.</h1>
        <p>
          Submit tracks, discover your group&apos;s listening history, and
          publish each finished round to Spotify.
        </p>
        <a className="button" href="/api/v1/auth/login">
          Sign in
        </a>
      </section>
    </main>
  );
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
    <>
      <a className="skip-link" href="#main-content">
        Skip to main content
      </a>
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
