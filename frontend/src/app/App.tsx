import { useMutation, useQuery } from "@tanstack/react-query";
import { lazy, Suspense, useEffect, type ReactNode } from "react";
import { ChevronRight, ListMusic, Sparkles } from "lucide-react";
import { Link, Navigate, Route, Routes, useParams, useSearchParams } from "react-router";

import { api, post } from "../api/client";
import { queryKeys } from "../api/queryKeys";
import type { components } from "../api/schema";
import { AppShell } from "../components/layout/AppShell";
import { Button, buttonVariants } from "../components/ui/button";
import { StatePanel } from "../components/ui/StatePanel";
import { ToastProvider } from "../components/ui/ToastProvider";
import { HomePage } from "../features/home/HomePage";

type Session = components["schemas"]["SessionResponse"];

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
const SettingsPage = lazy(() =>
  import("../features/profiles/SettingsPage").then((module) => ({
    default: module.SettingsPage,
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
          <a data-slot="button" className={buttonVariants()} href="/api/v1/auth/login">
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
  // Accepting is a write, so it is a mutation fired once the session is
  // known - a query here would re-POST on every window focus or remount.
  const accept = useMutation({
    mutationFn: (inviteToken: string) =>
      post<{ seriesId: string }>(`/series/invites/${inviteToken}/accept`, {}),
  });
  const { mutate: acceptInvite } = accept;
  useEffect(() => {
    if (token && session.isSuccess) acceptInvite(token);
  }, [acceptInvite, session.isSuccess, token]);
  if (session.isLoading || accept.isPending || (session.isSuccess && accept.isIdle))
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
          <Button
            render={
              <a href={`/api/v1/auth/login?return=${encodeURIComponent(`/invites/${token}`)}`} />
            }
          >
            Sign in
          </Button>
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
                <HomePage signedOut={<LandingPage />} />
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
          <Route
            path="/settings"
            element={
              <ShellRoute>
                <LazyRoute>
                  <SettingsPage />
                </LazyRoute>
              </ShellRoute>
            }
          />
          <Route path="/settings/connections" element={<Navigate to="/settings" replace />} />
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
