import { useCallback, useEffect, useMemo, useState } from "react";

type AuthState = "loading" | "unauthenticated" | "authenticated" | "forbidden";

interface UserSummary {
  id: number;
  username: string;
  display_name?: string | null;
  role: string;
  email?: string | null;
}

interface HealthResponse {
  status: string;
  timestamp: string;
}

function LoginPage({ onLogin, loading, error }: { onLogin: () => void; loading: boolean; error: string | null }) {
  return (
    <main className="shell">
      <section className="card">
        <h1>Boro Boys Music</h1>
        <p>Sign in with Spotify to access the playlist workspace.</p>
        <button onClick={onLogin} disabled={loading} className="primary">
          {loading ? "Contacting Spotify…" : "Continue with Spotify"}
        </button>
        {error && <p className="error">{error}</p>}
      </section>
    </main>
  );
}

function ForbiddenPage() {
  return (
    <main className="shell">
      <section className="card">
        <h1>Awaiting Access</h1>
        <p>Your account is not yet whitelisted for the Boro Boys workspace. Ask an admin for an invite.</p>
      </section>
    </main>
  );
}

function Dashboard({ user, health, onLogout }: { user: UserSummary; health: HealthResponse | null; onLogout: () => void }) {
  const name = user.display_name?.trim() || user.username;
  return (
    <main className="shell">
      <header className="card header">
        <div>
          <h1>Welcome, {name}</h1>
          <p className="muted">Role: {user.role}</p>
        </div>
        <button onClick={onLogout} className="secondary">
          Log out
        </button>
      </header>

      <section className="card">
        <h2>API Health</h2>
        {health ? (
          <dl className="metadata">
            <div>
              <dt>Status</dt>
              <dd>{health.status}</dd>
            </div>
            <div>
              <dt>Timestamp</dt>
              <dd>{new Date(health.timestamp).toLocaleString()}</dd>
            </div>
          </dl>
        ) : (
          <p className="muted">Loading service status…</p>
        )}
      </section>

      <section className="card">
        <h2>Next Steps</h2>
        <ul className="bullets">
          <li>Song submission workflow</li>
          <li>Playlist review tools</li>
          <li>Admin invite management</li>
        </ul>
      </section>
    </main>
  );
}

async function fetchJson<T>(input: RequestInfo, init?: RequestInit) {
  const response = await fetch(input, {
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
    ...init,
  });

  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || response.statusText);
  }

  return (await response.json()) as T;
}

export function App() {
  const [authState, setAuthState] = useState<AuthState>("loading");
  const [authError, setAuthError] = useState<string | null>(null);
  const [user, setUser] = useState<UserSummary | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [loginInFlight, setLoginInFlight] = useState(false);

  const loadUser = useCallback(async () => {
    try {
      const response = await fetch("/api/v1/users/me", { credentials: "include" });
      if (response.status === 200) {
        const payload = (await response.json()) as UserSummary;
        setUser(payload);
        setAuthState("authenticated");
      } else if (response.status === 403) {
        setUser(null);
        setAuthState("forbidden");
      } else {
        setUser(null);
        setAuthState("unauthenticated");
      }
    } catch (error) {
      console.error("Failed to load user", error);
      setAuthState("unauthenticated");
    }
  }, []);

  useEffect(() => {
    loadUser();
  }, [loadUser]);

  useEffect(() => {
    if (authState === "authenticated") {
      fetch("/api/v1/health", { credentials: "include" })
        .then(async (res) => {
          if (!res.ok) {
            throw new Error(res.statusText);
          }
          return res.json();
        })
        .then((payload: HealthResponse) => setHealth(payload))
        .catch((error) => {
          console.error("Failed to load health", error);
        });
    } else {
      setHealth(null);
    }
  }, [authState]);

  const handleLogin = useCallback(async () => {
    setAuthError(null);
    setLoginInFlight(true);
    try {
      const redirect_to = window.location.href;
      const query = new URLSearchParams({ redirect_to });
      const payload = await fetchJson<{ authorization_url: string; state: string }>(
        `/api/v1/auth/login?${query.toString()}`,
        { method: "GET" }
      );
      window.location.href = payload.authorization_url;
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unable to start login.";
      setAuthError(message);
      setLoginInFlight(false);
    }
  }, []);

  const handleLogout = useCallback(async () => {
    try {
      await fetch("/api/v1/auth/logout", {
        method: "POST",
        credentials: "include",
      });
    } finally {
      setUser(null);
      setAuthState("unauthenticated");
    }
  }, []);

  const body = useMemo(() => {
    if (authState === "loading") {
      return (
        <main className="shell">
          <section className="card">
            <p className="muted">Checking your session…</p>
          </section>
        </main>
      );
    }

    if (authState === "unauthenticated") {
      return <LoginPage onLogin={handleLogin} loading={loginInFlight} error={authError} />;
    }

    if (authState === "forbidden") {
      return <ForbiddenPage />;
    }

    if (user) {
      return <Dashboard user={user} health={health} onLogout={handleLogout} />;
    }

    return null;
  }, [authState, authError, handleLogin, handleLogout, health, loginInFlight, user]);

  return (
    <>
      <style>{globalStyles}</style>
      {body}
    </>
  );
}

const globalStyles = `
  :root {
    color-scheme: dark light;
    font-family: "Inter", system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    background: radial-gradient(circle at top, #0b1120, #020617 40%, #000000 100%);
    color: #e2e8f0;
  }

  * {
    box-sizing: border-box;
  }

  body, html, #root {
    margin: 0;
    min-height: 100%;
  }

  button {
    cursor: pointer;
    border: none;
    border-radius: 0.75rem;
    padding: 0.75rem 1.5rem;
    font-weight: 600;
    transition: transform 0.15s ease, box-shadow 0.15s ease;
  }

  button.primary {
    background: linear-gradient(135deg, #22d3ee, #6366f1);
    color: #0f172a;
    box-shadow: 0 12px 30px rgba(99, 102, 241, 0.35);
  }

  button.primary:disabled {
    opacity: 0.7;
    cursor: wait;
    box-shadow: none;
  }

  button.secondary {
    background: rgba(30, 41, 59, 0.9);
    color: #e2e8f0;
  }

  button:hover:not(:disabled) {
    transform: translateY(-1px);
  }

  .shell {
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 2.5rem;
  }

  .card {
    background: rgba(15, 23, 42, 0.82);
    border: 1px solid rgba(148, 163, 184, 0.2);
    border-radius: 1.25rem;
    padding: 2rem 2.5rem;
    width: min(540px, 100%);
    box-shadow: 0 25px 60px rgba(15, 23, 42, 0.5);
  }

  .header {
    width: min(640px, 100%);
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1.5rem;
    margin-bottom: 1.5rem;
  }

  h1 {
    margin: 0 0 0.75rem;
    font-size: clamp(1.75rem, 4vw, 2.5rem);
  }

  h2 {
    margin-top: 0;
    margin-bottom: 1rem;
  }

  p {
    margin: 0.5rem 0;
  }

  .muted {
    color: rgba(148, 163, 184, 0.85);
  }

  .error {
    color: #fca5a5;
    margin-top: 1rem;
  }

  .metadata {
    display: grid;
    gap: 0.75rem;
  }

  .metadata dt {
    font-weight: 600;
    color: rgba(94, 234, 212, 0.9);
  }

  .metadata dd {
    margin: 0;
  }

  .bullets {
    margin: 0;
    padding-left: 1.5rem;
    display: grid;
    gap: 0.5rem;
  }

  @media (max-width: 640px) {
    .shell {
      padding: 1.5rem;
    }

    .card {
      padding: 1.75rem;
    }

    .header {
      flex-direction: column;
      align-items: flex-start;
    }
  }
`;

export default App;
