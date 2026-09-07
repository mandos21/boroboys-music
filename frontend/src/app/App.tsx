import { useQuery } from "@tanstack/react-query";
import { ChevronRight, ListMusic, Sparkles } from "lucide-react";
import { Link, Navigate, Route, Routes, useSearchParams } from "react-router";

import { api } from "../api/client";
import { AppShell } from "../components/layout/AppShell";
import { StatePanel } from "../components/ui/StatePanel";
import { ToastProvider } from "../components/ui/ToastProvider";
import { AdminRoundPage, AdminSeriesPage, SeriesCreatePanel } from "../features/admin/AdminPages";
import { ConnectionsPage } from "../features/connections/ConnectionsPage";
import { RoundPage, SeriesPage } from "../features/rounds/RoundPages";
import { SubmissionPage } from "../features/submissions/SubmissionPage";
import { formatDate } from "../lib/format";

type Session = { user: { id: string; email: string | null; displayName: string | null; platformRole: string } };
type RoundPreview = { id: string; title: string; status: string; opensAt: string; closesAt: string; publishAt: string };
type SeriesPreview = { id: string; name: string; description: string | null; timezone: string; isAdmin: boolean; featuredRound: RoundPreview | null };

function HomePage() {
  const session = useQuery({ queryKey: ["session"], queryFn: () => api<Session>("/auth/session"), retry: false });
  const series = useQuery({ queryKey: ["series"], queryFn: () => api<SeriesPreview[]>("/series"), enabled: session.isSuccess });
  if (session.isLoading) return <LoadingPage message="Getting your music space ready…" />;
  if (session.isError || !session.data) return <LandingPage />;

  const currentUser = session.data.user;
  const items = series.data ?? [];
  return (
    <main className="shell page-shell dashboard-shell">
      <header className="page-heading dashboard-heading">
        <div>
          <p className="eyebrow">Your listening room</p>
          <h1>Good to have you here, {currentUser.displayName ?? "listener"}.</h1>
          <p>Keep up with what your friends have been into, leave a few things you cannot stop playing, and come back when the playlist lands.</p>
        </div>
        <div className="dashboard-meta" aria-label="Series overview"><ListMusic aria-hidden="true" size={20} /><span>{items.length} series</span></div>
      </header>
      {currentUser.platformRole === "admin" && <SeriesCreatePanel />}
      <section aria-labelledby="series-heading" className="content-section">
        <div className="section-heading"><div><h2 id="series-heading">Series</h2></div></div>
        {series.isLoading && <StatePanel kind="loading" title="Finding your series">This usually takes just a moment.</StatePanel>}
        {series.isError && <StatePanel kind="error" title="We couldn’t load your series">Refresh the page to try again.</StatePanel>}
        {series.data?.length === 0 && <StatePanel title="No series yet">Once you are added to a series, its active round and listening history will appear here.</StatePanel>}
        <div className="series-card-grid">{items.map((item) => <SeriesCard key={item.id} series={item} />)}</div>
      </section>
    </main>
  );
}

function SeriesCard({ series }: { series: SeriesPreview }) {
  const round = series.featuredRound;
  const isActive = round && round.status !== "published";
  return (
    <article className="series-card">
      <Link aria-label={`Open ${series.name}`} className="series-card-link-to-series" to={`/series/${series.id}`} />
      <div className="series-card-heading"><div><p className="eyebrow">{series.timezone}</p><h3>{series.name}</h3></div>{round && <span className={`status ${round.status}`}>{round.status}</span>}</div>
      <p>{series.description ?? "A place to trade what you have been listening to."}</p>
      {round ? (
        <Link className="series-card-round series-card-round-link" to={`/rounds/${round.id}`}><span>{isActive ? "Current round" : "Latest release"}</span><strong>{round.title}</strong><small>{isActive ? <>Closes {formatDate(round.closesAt)}</> : <>Released {formatDate(round.publishAt)}</>}</small></Link>
      ) : <div className="series-card-round series-card-empty"><span>No rounds yet</span><small>Its first listening window will show up here.</small></div>}
    </article>
  );
}

function LandingPage() {
  return <main className="shell landing-shell"><section className="landing-hero"><div className="landing-copy"><p className="eyebrow"><Sparkles aria-hidden="true" size={15} /> Music for the group chat</p><h1>What have you been listening to?</h1><p>BoroCrew Music is for passing songs around with friends—monthly favorites, a strange theme somebody picked, or whatever has been stuck in your head lately.</p><a className="button" href="/api/v1/auth/login">Sign in to BoroCrew Music <ChevronRight aria-hidden="true" size={18} /></a></div><aside className="landing-card" aria-label="How BoroCrew Music works"><span className="landing-card-icon"><ListMusic aria-hidden="true" size={25} /></span><h2>Keep the thread going.</h2><ol><li>Pick something for the prompt or moment.</li><li>See what everyone else has brought in.</li><li>Meet the finished playlist when it is ready.</li></ol></aside></section></main>;
}

function LoadingPage({ message }: { message: string }) { return <main className="shell page-shell"><StatePanel kind="loading" title={message}>Checking your session and available series.</StatePanel></main>; }
function SignedOutPage() { return <main className="shell narrow-page-shell"><StatePanel title="You’ve been signed out">Thanks for spending time with your group. <Link to="/">Return to BoroCrew Music</Link></StatePanel></main>; }

function AuthErrorPage() {
  const [searchParams] = useSearchParams();
  const reason = searchParams.get("reason");
  const message = { "oidc-unavailable": "The identity provider is unavailable or has not been configured yet. Try again shortly, or ask an administrator to check the sign-in setup.", denied: "The sign-in request was cancelled or denied by the identity provider. You can try again whenever you’re ready.", "expired-request": "That sign-in request has expired. Start a fresh sign-in to continue.", "email-verification-required": "Your identity provider needs to verify your email address before BoroCrew Music can create your account.", "provisioning-disabled": "New accounts are not being created automatically right now. Ask an administrator to enable access for you.", "account-inactive": "This account is currently inactive. Ask an administrator if you believe that is a mistake." }[reason ?? ""] ?? "The identity provider did not complete the request. Return home and try again, or check the provider configuration if this keeps happening.";
  return <main className="shell narrow-page-shell"><StatePanel kind="error" title="We couldn’t sign you in">{message} <a href="/api/v1/auth/login">Try signing in again</a></StatePanel></main>;
}

function NotFoundPage() { return <main className="shell narrow-page-shell"><StatePanel title="This page isn’t here">It may have moved, or the link may be out of date. <Link to="/">Go to your series</Link></StatePanel></main>; }
function ShellRoute({ children }: { children: React.ReactNode }) { return <AppShell>{children}</AppShell>; }

export function App() {
  return <ToastProvider><a className="skip-link" href="#main-content">Skip to main content</a><div id="main-content" tabIndex={-1}><Routes>
    <Route path="/" element={<ShellRoute><HomePage /></ShellRoute>} />
    <Route path="/rounds/:roundId" element={<ShellRoute><RoundPage /></ShellRoute>} />
    <Route path="/rounds/:roundId/submit" element={<ShellRoute><SubmissionPage /></ShellRoute>} />
    <Route path="/series/:seriesId" element={<ShellRoute><SeriesPage /></ShellRoute>} />
    <Route path="/profile" element={<ShellRoute><ConnectionsPage /></ShellRoute>} />
    <Route path="/settings/connections" element={<Navigate to="/profile" replace />} />
    <Route path="/admin" element={<Navigate to="/" replace />} />
    <Route path="/admin/series/:seriesId" element={<ShellRoute><AdminSeriesPage /></ShellRoute>} />
    <Route path="/admin/rounds/:roundId" element={<ShellRoute><AdminRoundPage /></ShellRoute>} />
    <Route path="/signed-out" element={<ShellRoute><SignedOutPage /></ShellRoute>} />
    <Route path="/auth/error" element={<ShellRoute><AuthErrorPage /></ShellRoute>} />
    <Route path="*" element={<ShellRoute><NotFoundPage /></ShellRoute>} />
  </Routes></div></ToastProvider>;
}
