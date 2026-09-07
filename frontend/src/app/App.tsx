import { useQuery } from "@tanstack/react-query";
import { CalendarDays, ChevronRight, Clock3, ListMusic, Sparkles } from "lucide-react";
import { Link, Route, Routes, useSearchParams } from "react-router";

import { api } from "../api/client";
import { AppShell } from "../components/layout/AppShell";
import { StatePanel } from "../components/ui/StatePanel";
import { ToastProvider } from "../components/ui/ToastProvider";
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
  seriesId: string;
  title: string;
  status: string;
  closesAt: string;
  publishAt: string;
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

  if (session.isLoading) return <LoadingPage message="Getting your music space ready…" />;
  if (session.isError || !session.data) return <LandingPage />;

  const currentUser = session.data.user;
  const actionableRounds = (rounds.data ?? []).filter((round) => !["published", "cancelled"].includes(round.status));
  const historySeries = [...new Set((rounds.data ?? []).filter((round) => round.status === "published").map((round) => round.seriesId))];
  return (
    <main className="shell page-shell dashboard-shell">
      <header className="page-heading dashboard-heading">
        <div>
          <p className="eyebrow">Your listening room</p>
          <h1>Good to have you here, {currentUser.displayName ?? "listener"}.</h1>
          <p>Choose a round, share something worth hearing, and follow the music your group is making together.</p>
        </div>
        <div className="dashboard-meta" aria-label="Round overview">
          <ListMusic aria-hidden="true" size={20} />
          <span>{actionableRounds.length} active round{actionableRounds.length === 1 ? "" : "s"}</span>
        </div>
      </header>
      <section aria-labelledby="rounds-heading" className="content-section">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Current &amp; upcoming</p>
            <h2 id="rounds-heading">Your rounds</h2>
          </div>
          <Link className="text-link" to="/settings/connections">
            Manage services <ChevronRight aria-hidden="true" size={17} />
          </Link>
        </div>
        {rounds.isLoading && <StatePanel kind="loading" title="Finding your rounds">This usually takes just a moment.</StatePanel>}
        {rounds.isError && <StatePanel kind="error" title="We couldn’t load your rounds">Refresh the page to try again.</StatePanel>}
        {rounds.data?.length === 0 && (
          <StatePanel title="Nothing scheduled for you yet">When an administrator adds you to a round, it will appear here with everything you need to participate.</StatePanel>
        )}
        {rounds.data && actionableRounds.length === 0 && rounds.data.length > 0 && (
          <StatePanel title="No current rounds">Your completed listening history is still here. {historySeries.length > 0 && <Link to={`/series/${historySeries[0]}`}>Browse series history</Link>}</StatePanel>
        )}
        <div className="round-grid">
          {actionableRounds.map((round) => (
            <article className="round-card" key={round.id}>
              <div className="round-card-topline">
                <span className={`status ${round.status}`}>{round.status}</span>
                <span className="round-card-limit">{round.submissionLimit} track{round.submissionLimit === 1 ? "" : "s"}</span>
              </div>
              <h3>{round.title}</h3>
              <dl>
                <div>
                  <dt><Clock3 aria-hidden="true" size={15} /> Closes</dt>
                  <dd>{formatDate(round.closesAt)}</dd>
                </div>
                <div>
                  <dt><CalendarDays aria-hidden="true" size={15} /> Releases</dt>
                  <dd>{formatDate(round.publishAt)}</dd>
                </div>
              </dl>
              <Link className="card-action" to={`/rounds/${round.id}`}>
                Open round <ChevronRight aria-hidden="true" size={18} />
              </Link>
            </article>
          ))}
        </div>
        {historySeries.length > 0 && actionableRounds.length > 0 && (
          <div className="dashboard-history-link"><ListMusic aria-hidden="true" size={17} /><span>Looking for a past playlist?</span><Link className="dashboard-history-action" to={`/series/${historySeries[0]}`}>Browse series history <ChevronRight aria-hidden="true" size={16} /></Link></div>
        )}
      </section>
    </main>
  );
}

function LandingPage() {
  return (
    <main className="shell landing-shell">
      <section className="landing-hero">
        <div className="landing-copy">
          <p className="eyebrow"><Sparkles aria-hidden="true" size={15} /> Music for the group chat</p>
          <h1>Give every listening session a little more intention.</h1>
          <p>Music Rounds is a private home for timed recommendations, shared listening history, and playlists your group will actually return to.</p>
          <a className="button" href="/api/v1/auth/login">
            Sign in to your rounds <ChevronRight aria-hidden="true" size={18} />
          </a>
        </div>
        <aside className="landing-card" aria-label="How Music Rounds works">
          <span className="landing-card-icon"><ListMusic aria-hidden="true" size={25} /></span>
          <h2>A better ritual for sharing music.</h2>
          <ol>
            <li>Choose tracks within your group’s window.</li>
            <li>See listening context when it’s shared.</li>
            <li>Meet the finished playlist on release day.</li>
          </ol>
        </aside>
      </section>
    </main>
  );
}

function LoadingPage({ message }: { message: string }) {
  return (
    <main className="shell page-shell">
      <StatePanel kind="loading" title={message}>Checking your session and available rounds.</StatePanel>
    </main>
  );
}

function SignedOutPage() {
  return (
    <main className="shell narrow-page-shell">
      <StatePanel title="You’ve been signed out">Thanks for spending time with your group. <Link to="/">Return to Music Rounds</Link></StatePanel>
    </main>
  );
}

function AuthErrorPage() {
  const [searchParams] = useSearchParams();
  const reason = searchParams.get("reason");
  const message = {
    "oidc-unavailable": "The identity provider is unavailable or has not been configured yet. Try again shortly, or ask an administrator to check the sign-in setup.",
    denied: "The sign-in request was cancelled or denied by the identity provider. You can try again whenever you’re ready.",
    "expired-request": "That sign-in request has expired. Start a fresh sign-in to continue.",
    "email-verification-required": "Your identity provider needs to verify your email address before Music Rounds can create your account.",
    "provisioning-disabled": "New accounts are not being created automatically right now. Ask an administrator to enable access for you.",
    "account-inactive": "This account is currently inactive. Ask an administrator if you believe that is a mistake.",
  }[reason ?? ""] ?? "The identity provider did not complete the request. Return home and try again, or check the provider configuration if this keeps happening.";

  return (
    <main className="shell narrow-page-shell">
      <StatePanel kind="error" title="We couldn’t sign you in">
        {message} <a href="/api/v1/auth/login">Try signing in again</a>
      </StatePanel>
    </main>
  );
}

function NotFoundPage() {
  return (
    <main className="shell narrow-page-shell">
      <StatePanel title="This page isn’t here">It may have moved, or the link may be out of date. <Link to="/">Go to your rounds</Link></StatePanel>
    </main>
  );
}

function ShellRoute({ children }: { children: React.ReactNode }) {
  return <AppShell>{children}</AppShell>;
}

export function App() {
  return (
    <ToastProvider>
      <a className="skip-link" href="#main-content">Skip to main content</a>
      <div id="main-content" tabIndex={-1}>
        <Routes>
          <Route path="/" element={<ShellRoute><HomePage /></ShellRoute>} />
          <Route path="/rounds/:roundId" element={<ShellRoute><RoundPage /></ShellRoute>} />
          <Route path="/rounds/:roundId/submit" element={<ShellRoute><SubmissionPage /></ShellRoute>} />
          <Route path="/series/:seriesId" element={<ShellRoute><SeriesPage /></ShellRoute>} />
          <Route path="/settings/connections" element={<ShellRoute><ConnectionsPage /></ShellRoute>} />
          <Route path="/admin" element={<ShellRoute><AdminIndexPage /></ShellRoute>} />
          <Route path="/admin/series/:seriesId" element={<ShellRoute><AdminSeriesPage /></ShellRoute>} />
          <Route path="/admin/rounds/:roundId" element={<ShellRoute><AdminRoundPage /></ShellRoute>} />
          <Route path="/signed-out" element={<ShellRoute><SignedOutPage /></ShellRoute>} />
          <Route path="/auth/error" element={<ShellRoute><AuthErrorPage /></ShellRoute>} />
          <Route path="*" element={<ShellRoute><NotFoundPage /></ShellRoute>} />
        </Routes>
      </div>
    </ToastProvider>
  );
}
