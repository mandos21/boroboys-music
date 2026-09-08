import { useQuery } from "@tanstack/react-query";
import { lazy, Suspense, type CSSProperties, type ReactNode } from "react";
import { ChevronRight, ListMusic, Sparkles } from "lucide-react";
import { Link, Navigate, Route, Routes, useParams, useSearchParams } from "react-router";

import { api, post } from "../api/client";
import { queryKeys } from "../api/queryKeys";
import type { components } from "../api/schema";
import { AppShell } from "../components/layout/AppShell";
import { StatePanel } from "../components/ui/StatePanel";
import { ToastProvider } from "../components/ui/ToastProvider";
import { SeriesCreatePanel } from "../features/admin/AdminPages";
import { formatDate } from "../lib/format";

type Session = components["schemas"]["SessionResponse"];
type SeriesPreview = components["schemas"]["SeriesListResponse"];

// The dashboard is the usual first view. Keep its initial payload lean and
// load the richer workspace screens only when somebody navigates to them.
const RoundPage = lazy(() =>
  import("../features/rounds/RoundPages").then((module) => ({ default: module.RoundPage })),
);
const SeriesPage = lazy(() =>
  import("../features/rounds/RoundPages").then((module) => ({ default: module.SeriesPage })),
);
const SubmissionPage = lazy(() =>
  import("../features/submissions/SubmissionPage").then((module) => ({
    default: module.SubmissionPage,
  })),
);
const ProfilePage = lazy(() =>
  import("../features/profiles/ProfilePage").then((module) => ({ default: module.ProfilePage })),
);
const ContributorProfilePage = lazy(() =>
  import("../features/profiles/ProfilePage").then((module) => ({
    default: module.ContributorProfilePage,
  })),
);
const AdminSeriesPage = lazy(() =>
  import("../features/admin/AdminSeriesPage").then((module) => ({
    default: module.AdminSeriesPage,
  })),
);
const AdminRoundPage = lazy(() =>
  import("../features/admin/AdminRoundPage").then((module) => ({ default: module.AdminRoundPage })),
);

function seriesAccent(series: SeriesPreview) {
  if (series.accentColor) return series.accentColor;
  // A stable companion color without processing remote artwork in the browser.
  const seed = series.coverImageUrl ?? series.fallbackArtworkUrl ?? series.name;
  const hash = [...seed].reduce(
    (value, character) => (value * 31 + character.charCodeAt(0)) >>> 0,
    7,
  );
  return ["#15803d", "#0f766e", "#4d7c0f", "#9a3412", "#7e22ce"][hash % 5];
}

function HomePage() {
  const session = useQuery({
    queryKey: queryKeys.session(),
    queryFn: () => api<Session>("/auth/session"),
    retry: false,
  });
  const series = useQuery({
    queryKey: queryKeys.series(),
    queryFn: () => api<SeriesPreview[]>("/series"),
    enabled: session.isSuccess,
  });
  if (session.isLoading) return <LoadingPage message="Getting your music space ready…" />;
  if (session.isError || !session.data) return <LandingPage />;

  const currentUser = session.data.user;
  const items = series.data ?? [];
  const openSeries = items.find((item) => item.featuredRound?.status === "open");
  const otherSeries = openSeries ? items.filter((item) => item.id !== openSeries.id) : items;
  return (
    <main className="shell page-shell dashboard-shell">
      <header className="page-heading dashboard-heading">
        <div>
          <p className="eyebrow">Your listening room</p>
          <h1>
            Good to have you here,{" "}
            <span className="dashboard-user-name">{currentUser.displayName ?? "listener"}</span>.
          </h1>
          <p>
            Keep up with what your friends have been into, leave a few things you cannot stop
            playing, and come back when the playlist lands.
          </p>
        </div>
        <div className="dashboard-meta" aria-label="Series overview">
          <ListMusic aria-hidden="true" size={20} />
          <span>{items.length} series</span>
        </div>
      </header>
      {openSeries && <FeaturedOpenSeries series={openSeries} />}
      <section aria-labelledby="series-heading" className="content-section">
        <div className="section-heading">
          <div>
            <h2 id="series-heading">{openSeries ? "Other series" : "Series"}</h2>
          </div>
        </div>
        {series.isLoading && (
          <StatePanel kind="loading" title="Finding your series">
            This usually takes just a moment.
          </StatePanel>
        )}
        {series.isError && (
          <StatePanel kind="error" title="We couldn’t load your series">
            Refresh the page to try again.
          </StatePanel>
        )}
        {series.data?.length === 0 && (
          <StatePanel title="No series yet">
            Once you are added to a series, its active round and listening history will appear here.
          </StatePanel>
        )}
        <div className="series-card-grid">
          {otherSeries.map((item) => (
            <SeriesCard key={item.id} series={item} />
          ))}
        </div>
      </section>
      {currentUser.platformRole === "admin" && <SeriesCreatePanel />}
    </main>
  );
}

function FeaturedOpenSeries({ series }: { series: SeriesPreview }) {
  const round = series.featuredRound;
  const cover = series.coverImageUrl ?? series.fallbackArtworkUrl;
  if (!round) return null;
  return (
    <article
      className="featured-open-series"
      style={
        {
          "--series-accent": seriesAccent(series),
          "--series-cover": cover ? `url(${cover})` : "none",
        } as CSSProperties
      }
    >
      <Link
        aria-label={`Open ${series.name}`}
        className="featured-open-series-link"
        to={`/series/${series.id}`}
      />
      <div className="featured-open-series-copy">
        <p className="eyebrow open-now-label">
          <RoundPulse />
          Open now
        </p>
        <h2>{series.name}</h2>
        <p>{series.description ?? "A place to trade what you have been listening to."}</p>
        <p className="next-action">Your next step: pick a track for this round.</p>
      </div>
      <Link className="featured-open-series-round" to={`/rounds/${round.id}`}>
        <span>Current round</span>
        <strong>{round.title}</strong>
        <small>
          {round.submittedCount} of {round.contributorCount} people have submitted
        </small>
        <progress
          aria-label={`${round.submittedCount} of ${round.contributorCount} contributors have submitted`}
          max={Math.max(round.contributorCount, 1)}
          value={round.submittedCount}
        />
        <small>Closes {formatDate(round.closesAt)}</small>
        {round.prompt && <small className="featured-prompt">Prompt: {round.prompt}</small>}
      </Link>
    </article>
  );
}

function RoundPulse() {
  return (
    <span className="round-pulse" aria-label="Round is open">
      <i />
      <i />
      <i />
    </span>
  );
}

function SeriesCard({ series }: { series: SeriesPreview }) {
  const round = series.featuredRound;
  const isActive = round && round.status !== "published";
  const isOpen = round?.status === "open";
  const cover = series.coverImageUrl ?? series.fallbackArtworkUrl;
  return (
    <article
      className="series-card"
      style={
        {
          "--series-accent": seriesAccent(series),
          "--series-cover": cover ? `url(${cover})` : "none",
        } as CSSProperties
      }
    >
      <Link
        aria-label={`Open ${series.name}`}
        className="series-card-link-to-series"
        to={`/series/${series.id}`}
      />
      <div className="series-card-heading">
        <div>
          <h3>{series.name}</h3>
        </div>
        <span>
          {isOpen && <RoundPulse />}
          {round && <span className={`status ${round.status}`}>{round.status}</span>}
        </span>
      </div>
      <p>{series.description ?? "A place to trade what you have been listening to."}</p>
      {round ? (
        <Link className="series-card-round series-card-round-link" to={`/rounds/${round.id}`}>
          <span>{isActive ? "Current round" : "Latest release"}</span>
          <strong>{round.title}</strong>
          <small>
            {isOpen ? (
              <>
                {round.submittedCount} of {round.contributorCount} people have submitted · closes{" "}
                {formatDate(round.closesAt)}
              </>
            ) : isActive ? (
              <>Opens {formatDate(round.opensAt)}</>
            ) : (
              <>Released {formatDate(round.publishAt)}</>
            )}
          </small>
          {isOpen && (
            <progress
              aria-label={`${round.submittedCount} of ${round.contributorCount} contributors have submitted`}
              max={Math.max(round.contributorCount, 1)}
              value={round.submittedCount}
            />
          )}
          {round.prompt && <small className="featured-prompt">Prompt: {round.prompt}</small>}
          {!isActive && (
            <small className="now-spinning">
              <span>Now spinning</span>
              <span className="now-spinning-viewport">
                <strong>{round.title}</strong>
              </span>
            </small>
          )}
        </Link>
      ) : (
        <div className="series-card-round series-card-empty">
          <span>No rounds yet</span>
          <small>Its first listening window will show up here.</small>
        </div>
      )}
    </article>
  );
}

function LandingPage() {
  return (
    <main className="shell landing-shell">
      <section className="landing-hero">
        <div className="landing-copy">
          <p className="eyebrow">
            <Sparkles aria-hidden="true" size={15} /> Music for the group chat
          </p>
          <h1>What have you been listening to?</h1>
          <p>
            BoroCrew Music is for passing songs around with friends—monthly favorites, a strange
            theme somebody picked, or whatever has been stuck in your head lately.
          </p>
          <a className="button" href="/api/v1/auth/login">
            Sign in to BoroCrew Music <ChevronRight aria-hidden="true" size={18} />
          </a>
        </div>
        <aside className="landing-card" aria-label="How BoroCrew Music works">
          <span className="landing-card-icon">
            <ListMusic aria-hidden="true" size={25} />
          </span>
          <h2>Keep the thread going.</h2>
          <ol>
            <li>Pick something for the prompt or moment.</li>
            <li>See what everyone else has brought in.</li>
            <li>Meet the finished playlist when it is ready.</li>
          </ol>
        </aside>
      </section>
    </main>
  );
}

function LoadingPage({ message }: { message: string }) {
  return (
    <main className="shell page-shell">
      <StatePanel kind="loading" title={message}>
        Checking your session and available series.
      </StatePanel>
    </main>
  );
}
function SignedOutPage() {
  return (
    <main className="shell narrow-page-shell">
      <StatePanel title="You’ve been signed out">
        Thanks for spending time with your group. <Link to="/">Return to BoroCrew Music</Link>
      </StatePanel>
    </main>
  );
}

function InviteAcceptPage() {
  const { token } = useParams();
  const session = useQuery({
    queryKey: queryKeys.session(),
    queryFn: () => api<Session>("/auth/session"),
    retry: false,
  });
  const accept = useQuery({
    queryKey: queryKeys.acceptInvite(token),
    queryFn: () => post<{ seriesId: string }>(`/series/invites/${token}/accept`, {}),
    enabled: Boolean(token && session.isSuccess),
    retry: false,
  });
  if (session.isLoading || accept.isLoading)
    return (
      <main className="shell narrow-page-shell">
        <StatePanel kind="loading" title="Opening your invite">
          Adding you to the series.
        </StatePanel>
      </main>
    );
  if (session.isError)
    return (
      <main className="shell narrow-page-shell">
        <StatePanel title="Sign in to join this series">
          <a
            className="button"
            href={`/api/v1/auth/login?return=${encodeURIComponent(`/invites/${token}`)}`}
          >
            Sign in
          </a>
        </StatePanel>
      </main>
    );
  if (accept.isError || !accept.data)
    return (
      <main className="shell narrow-page-shell">
        <StatePanel kind="error" title="This invite is unavailable">
          It may have expired, been used up, or been revoked.
        </StatePanel>
      </main>
    );
  return <Navigate to={`/series/${accept.data.seriesId}`} replace />;
}

function AuthErrorPage() {
  const [searchParams] = useSearchParams();
  const reason = searchParams.get("reason");
  const message =
    {
      "oidc-unavailable":
        "The identity provider is unavailable or has not been configured yet. Try again shortly, or ask an administrator to check the sign-in setup.",
      denied:
        "The sign-in request was cancelled or denied by the identity provider. You can try again whenever you’re ready.",
      "expired-request": "That sign-in request has expired. Start a fresh sign-in to continue.",
      "invalid-request":
        "That sign-in link was incomplete or malformed. Start a fresh sign-in from the home page.",
      "verification-failed":
        "The identity provider’s response could not be verified. Start a fresh sign-in, or ask an administrator to check the provider configuration.",
      "email-verification-required":
        "Your identity provider needs to verify your email address before BoroCrew Music can create your account.",
      "provisioning-disabled":
        "New accounts are not being created automatically right now. Ask an administrator to enable access for you.",
      "account-inactive":
        "This account is currently inactive. Ask an administrator if you believe that is a mistake.",
    }[reason ?? ""] ??
    "The identity provider did not complete the request. Return home and try again, or check the provider configuration if this keeps happening.";
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
      <StatePanel title="This page isn’t here">
        It may have moved, or the link may be out of date. <Link to="/">Go to your series</Link>
      </StatePanel>
    </main>
  );
}
function ShellRoute({ children }: { children: ReactNode }) {
  return <AppShell>{children}</AppShell>;
}

function LazyRoute({ children }: { children: ReactNode }) {
  return <Suspense fallback={<LoadingPage message="Loading this page…" />}>{children}</Suspense>;
}

export function App() {
  return (
    <ToastProvider>
      <a className="skip-link" href="#main-content">
        Skip to main content
      </a>
      <div id="main-content" tabIndex={-1}>
        <Routes>
          <Route
            path="/"
            element={
              <ShellRoute>
                <HomePage />
              </ShellRoute>
            }
          />
          <Route
            path="/rounds/:roundId"
            element={
              <ShellRoute>
                <LazyRoute>
                  <RoundPage />
                </LazyRoute>
              </ShellRoute>
            }
          />
          <Route
            path="/rounds/:roundId/submit"
            element={
              <ShellRoute>
                <LazyRoute>
                  <SubmissionPage />
                </LazyRoute>
              </ShellRoute>
            }
          />
          <Route
            path="/series/:seriesId"
            element={
              <ShellRoute>
                <LazyRoute>
                  <SeriesPage />
                </LazyRoute>
              </ShellRoute>
            }
          />
          <Route
            path="/invites/:token"
            element={
              <ShellRoute>
                <InviteAcceptPage />
              </ShellRoute>
            }
          />
          <Route
            path="/profile"
            element={
              <ShellRoute>
                <LazyRoute>
                  <ProfilePage />
                </LazyRoute>
              </ShellRoute>
            }
          />
          <Route
            path="/people/:userId"
            element={
              <ShellRoute>
                <LazyRoute>
                  <ContributorProfilePage />
                </LazyRoute>
              </ShellRoute>
            }
          />
          <Route path="/settings/connections" element={<Navigate to="/profile" replace />} />
          <Route path="/admin" element={<Navigate to="/" replace />} />
          <Route
            path="/admin/series/:seriesId"
            element={
              <ShellRoute>
                <LazyRoute>
                  <AdminSeriesPage />
                </LazyRoute>
              </ShellRoute>
            }
          />
          <Route
            path="/admin/rounds/:roundId"
            element={
              <ShellRoute>
                <LazyRoute>
                  <AdminRoundPage />
                </LazyRoute>
              </ShellRoute>
            }
          />
          <Route
            path="/signed-out"
            element={
              <ShellRoute>
                <SignedOutPage />
              </ShellRoute>
            }
          />
          <Route
            path="/auth/error"
            element={
              <ShellRoute>
                <AuthErrorPage />
              </ShellRoute>
            }
          />
          <Route
            path="*"
            element={
              <ShellRoute>
                <NotFoundPage />
              </ShellRoute>
            }
          />
        </Routes>
      </div>
    </ToastProvider>
  );
}
