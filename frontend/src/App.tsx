import { useCallback, useEffect, useMemo, useState } from "react";

type AuthState = "loading" | "unauthenticated" | "authenticated" | "forbidden";
type Role = "member" | "admin";
type AppView = "submit" | "history" | "lookup" | "admin";

type UserSummary = {
  id: number;
  username: string;
  display_name?: string | null;
  role: Role;
  email?: string | null;
};

type InviteRecord = {
  id: number;
  token: string;
  email?: string | null;
  role: Role;
  expires_at?: string | null;
  created_at: string;
};

type TrackRead = {
  id: number;
  spotify_track_id: string;
  name: string;
  artist: string;
  album?: string | null;
  duration_ms?: number | null;
  spotify_url?: string | null;
};

type SubmissionRecord = {
  id: number;
  submission_month: string;
  notes?: string | null;
  is_locked: boolean;
  track: TrackRead;
};

type PlaylistTrack = {
  position: number;
  track: TrackRead;
  submitter_id?: number | null;
  submitter_name?: string | null;
};

type PlaylistRecord = {
  id: number;
  name: string;
  description?: string | null;
  month: string;
  spotify_playlist_id?: string | null;
  tracks: PlaylistTrack[];
};

type SpotifyTrackResult = {
  spotify_track_id: string;
  name: string;
  artist: string;
  album?: string | null;
  duration_ms?: number | null;
  spotify_url?: string | null;
};

type PlaylistImportTrack = SpotifyTrackResult & { position: number };

type PlaylistImportPayload = {
  spotify_playlist_id: string;
  name: string;
  description?: string | null;
  playlist_month: string;
  snapshot_id?: string | null;
  tracks: PlaylistImportTrack[];
};

function TopBar({ authState, user, activeView, onSelectView, onLogin, onLogout }: { authState: AuthState; user: UserSummary | null; activeView: AppView; onSelectView: (view: AppView) => void; onLogin: () => void; onLogout: () => void }) {
  const navOptions: Array<{ id: AppView; label: string }> = useMemo(() => {
    const options: Array<{ id: AppView; label: string }> = [
      { id: "submit", label: "Submit Track" },
      { id: "history", label: "Playlist History" },
      { id: "lookup", label: "Song Lookup" },
    ];
    if (user?.role === "admin") {
      options.push({ id: "admin", label: "Admin" });
    }
    return options;
  }, [user]);

  return (
    <header className="topbar">
      <div className="topbar__brand">Boro Crew Music</div>
      <nav className="topbar__nav">
        {navOptions.map(({ id, label }) => (
          <button
            key={id}
            type="button"
            className={`topbar__pill${id === activeView ? " topbar__pill--active" : ""}`}
            onClick={() => onSelectView(id)}
            disabled={authState !== "authenticated"}
          >
            {label}
          </button>
        ))}
      </nav>
      <div className="topbar__auth">
        {authState === "authenticated" && user ? (
          <>
            <span className="topbar__user">{user.display_name?.trim() || user.username}</span>
            <button className="secondary small" onClick={onLogout}>
              Log out
            </button>
          </>
        ) : authState === "unauthenticated" ? (
          <button className="primary small" onClick={onLogin}>
            Log in
          </button>
        ) : null}
      </div>
    </header>
  );
}

function LoginPage({ onLogin, loading, error }: { onLogin: () => void; loading: boolean; error: string | null }) {
  return (
    <section className="card auth">
      <h1>Boro Crew Music</h1>
      <p>Sign in with Spotify to access the monthly playlist tools.</p>
      <button onClick={onLogin} disabled={loading} className="primary">
        {loading ? "Contacting Spotify…" : "Continue with Spotify"}
      </button>
      {error && <p className="error">{error}</p>}
    </section>
  );
}

function ForbiddenPage() {
  return (
    <section className="card auth">
      <h1>Boro Crew Music</h1>
      <p>Your account is not yet whitelisted for this workspace. Ask an admin for an invite.</p>
    </section>
  );
}

function InviteForm({ onCreate, busy }: { onCreate: (payload: { email?: string | null; role: Role; expires_in_days: number }) => Promise<void>; busy: boolean }) {
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("member");
  const [expiresInDays, setExpiresInDays] = useState(7);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    try {
      await onCreate({ email: email.trim() ? email.trim() : null, role, expires_in_days: expiresInDays });
      setEmail("");
      setRole("member");
      setExpiresInDays(7);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unable to create invite";
      setError(message);
    }
  };

  return (
    <form className="invite-form" onSubmit={handleSubmit}>
      <div className="field">
        <label>Email (optional)</label>
        <input type="email" placeholder="friend@example.com" value={email} onChange={(event) => setEmail(event.target.value)} />
      </div>
      <div className="field-row">
        <label>Role</label>
        <select value={role} onChange={(event) => setRole(event.target.value as Role)}>
          <option value="member">Member</option>
          <option value="admin">Admin</option>
        </select>
      </div>
      <div className="field-row">
        <label>Expires in</label>
        <input min={1} max={30} type="number" value={expiresInDays} onChange={(event) => setExpiresInDays(Number(event.target.value))} />
        <span>days</span>
      </div>
      <button className="primary invite-button" type="submit" disabled={busy}>
        {busy ? "Creating…" : "Create invite"}
      </button>
      {error && <p className="error">{error}</p>}
    </form>
  );
}

function InvitesPanel({ invites, onRefresh, busy }: { invites: InviteRecord[]; onRefresh: () => void; busy: boolean }) {
  const sortedInvites = useMemo(() => invites.slice().sort((a, b) => (b.id ?? 0) - (a.id ?? 0)), [invites]);

  return (
    <section className="card">
      <div className="card__header">
        <h3>Active Invites</h3>
        <button className="secondary small" onClick={onRefresh} disabled={busy}>
          Refresh
        </button>
      </div>
      {sortedInvites.length === 0 ? (
        <p className="muted">No active invites yet. Generate one to onboard a new listener.</p>
      ) : (
        <div className="table">
          <div className="table__row table__row--head">
            <span>Token</span>
            <span>Email</span>
            <span>Role</span>
            <span>Expires</span>
          </div>
          {sortedInvites.map((invite) => (
            <div key={invite.id} className="table__row">
              <span className="token">{invite.token}</span>
              <span>{invite.email || "Any"}</span>
              <span className={invite.role === "admin" ? "pill pill--admin" : "pill"}>{invite.role}</span>
              <span>{invite.expires_at ? new Date(invite.expires_at).toLocaleString() : "No expiry"}</span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function SubmissionPanel({ submission, isLoading, isLocked, notes, onNotesChange, onSearch, searchQuery, onSearchQueryChange, searchResults, searchLoading, onSelectTrack, message, error }: { submission: SubmissionRecord | null; isLoading: boolean; isLocked: boolean; notes: string; onNotesChange: (value: string) => void; onSearch: () => void; searchQuery: string; onSearchQueryChange: (value: string) => void; searchResults: SpotifyTrackResult[]; searchLoading: boolean; onSelectTrack: (track: SpotifyTrackResult) => void; message: string | null; error: string | null }) {
  const handleSubmitSearch = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!isLocked) onSearch();
  };

  return (
    <section className="card">
      <div className="card__header">
        <h2>Submit Your Track</h2>
      </div>
      <p className="muted">Choose one track per month. Update it anytime until the playlist is locked.</p>

      <div className="submission-status">
        {isLoading ? (
          <p className="muted">Loading your current submission…</p>
        ) : submission ? (
          <div className="submission-card">
            <div>
              <span className="pill pill--spotify">Current pick</span>
              <h3>{submission.track.name}</h3>
              <p className="muted">{submission.track.artist}</p>
              {submission.track.album && <p className="muted small">Album: {submission.track.album}</p>}
              {submission.track.spotify_url && (
                <p>
                  <a className="link" href={submission.track.spotify_url} target="_blank" rel="noreferrer">
                    Open on Spotify
                  </a>
                </p>
              )}
            </div>
            <div className="submission-status__meta">
              <span className={submission.is_locked ? "pill pill--locked" : "pill"}>
                {submission.is_locked ? "Locked" : "Editable"}
              </span>
            </div>
          </div>
        ) : (
          <p className="muted">No submission for this month yet. Find a song below to add your pick.</p>
        )}
      </div>

      <label className="field">
        <span>Notes (optional)</span>
        <textarea
          rows={3}
          value={notes}
          onChange={(event) => onNotesChange(event.target.value)}
          placeholder="Share context or shout-outs for the playlist write-up."
          disabled={isLocked}
        />
      </label>

      <form className="submission-search" onSubmit={handleSubmitSearch}>
        <input type="search" placeholder="Search tracks on Spotify" value={searchQuery} onChange={(event) => onSearchQueryChange(event.target.value)} disabled={isLocked} />
        <button className="primary" type="submit" disabled={isLocked || searchLoading || !searchQuery.trim()}>
          {searchLoading ? "Searching…" : "Search"}
        </button>
      </form>
      {error && <p className="error">{error}</p>}
      {message && <p className="success">{message}</p>}

      {searchResults.length > 0 && !isLocked && (
        <div className="search-results">
          {searchResults.map((result) => (
            <button key={result.spotify_track_id} type="button" className="result" onClick={() => onSelectTrack(result)}>
              <div>
                <h4>{result.name}</h4>
                <p className="muted">{result.artist}</p>
                {result.album && <p className="muted small">{result.album}</p>}
              </div>
              <span className="pill pill--cta">Choose</span>
            </button>
          ))}
        </div>
      )}

      {isLocked && <p className="muted small">Submissions are locked once the playlist is finalized. Ask an admin if you need changes.</p>}
    </section>
  );
}

const formatPlaylistLabel = (playlist: PlaylistRecord) =>
  new Date(playlist.month).toLocaleString(undefined, { month: "long", year: "numeric" });

const formatDuration = (durationMs?: number | null) => {
  if (!durationMs) return "—";
  const totalSeconds = Math.floor(durationMs / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
};

function HistoryView({
  playlists,
  loading,
  onSelect,
  selected,
  detailLoading,
  detailError,
}: {
  playlists: PlaylistRecord[];
  loading: boolean;
  onSelect: (playlistId: number) => void;
  selected: PlaylistRecord | null;
  detailLoading: boolean;
  detailError: string | null;
}) {
  return (
    <section className="history-shell">
      <aside className="history-list">
        <h2>Playlist History</h2>
        {loading ? (
          <p className="muted">Loading playlists…</p>
        ) : playlists.length === 0 ? (
          <p className="muted">No playlists published yet.</p>
        ) : (
          playlists.map((playlist) => (
            <button
              key={playlist.id}
              type="button"
              className={`history-list__item${selected?.id === playlist.id ? " history-list__item--active" : ""}`}
              onClick={() => onSelect(playlist.id)}
            >
              <span>{formatPlaylistLabel(playlist)}</span>
              <span className="muted small">{playlist.tracks.length} tracks</span>
            </button>
          ))
        )}
      </aside>
      <section className="card history-detail">
        {detailLoading ? (
          <p className="muted">Loading playlist details…</p>
        ) : detailError ? (
          <p className="error">{detailError}</p>
        ) : selected ? (
          <div className="history-detail__content">
            <header>
              <h3>{formatPlaylistLabel(selected)}</h3>
              {selected.spotify_playlist_id && (
                <a className="link" href={`https://open.spotify.com/playlist/${selected.spotify_playlist_id}`} target="_blank" rel="noreferrer">
                  Open on Spotify
                </a>
              )}
              {selected.description && <p className="muted small">{selected.description}</p>}
            </header>
            <ul className="tracklist">
              {selected.tracks.map((entry) => (
                <li className="tracklist__item" key={`${selected.id}-${entry.position}`}>
                  <div className="tracklist__left">
                    <span className="tracklist__title">{entry.position}. {entry.track.name}</span>
                    <span className="tracklist__meta">{entry.track.artist}{entry.track.album ? ` · ${entry.track.album}` : ""}</span>
                  </div>
                  <div className="tracklist__right">
                    <span className="tracklist__duration">{formatDuration(entry.track.duration_ms)}</span>
                    {entry.submitter_name && <span className="tracklist__submitter">{entry.submitter_name}</span>}
                    {entry.track.spotify_url && (
                      <a className="pill pill--cta" href={entry.track.spotify_url} target="_blank" rel="noreferrer">
                        Open
                      </a>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          </div>
        ) : (
          <p className="muted">Select a playlist to see track details.</p>
        )}
      </section>
    </section>
  );
}

function LookupPanel({ query, onQueryChange, onSearch, loading, results, error }: { query: string; onQueryChange: (value: string) => void; onSearch: () => void; loading: boolean; results: SpotifyTrackResult[]; error: string | null }) {
  const handleSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    onSearch();
  };

  return (
    <section className="card">
      <div className="card__header">
        <h2>Song Lookup</h2>
      </div>
      <form className="lookup-form" onSubmit={handleSubmit}>
        <div className="field">
          <label>Search term</label>
          <input type="search" placeholder="Artist, track, or album" value={query} onChange={(event) => onQueryChange(event.target.value)} />
        </div>
        <button className="primary" type="submit" disabled={!query.trim() || loading}>
          {loading ? "Searching…" : "Search"}
        </button>
      </form>
      {error && <p className="error">{error}</p>}
      {loading ? (
        <p className="muted">Searching Spotify…</p>
      ) : results.length > 0 ? (
        <div className="search-results">
          {results.map((result) => (
            <div key={result.spotify_track_id} className="result result--static">
              <div>
                <h4>{result.name}</h4>
                <p className="muted">
                  {result.artist}
                  {result.album ? ` · ${result.album}` : ""}
                </p>
              </div>
              {result.spotify_url && (
                <a className="pill pill--cta" href={result.spotify_url} target="_blank" rel="noreferrer">
                  Open
                </a>
              )}
            </div>
          ))}
        </div>
      ) : (
        <p className="muted">No results yet. Try searching for a track.</p>
      )}
    </section>
  );
}

function AdminPlaylistImport({ users, onImport, busy, payload, onSave, saving, assignments, onAssignmentChange, lockSubmissions, onToggleLock, statusMessage }: { users: UserSummary[]; onImport: (ref: string, month: string) => Promise<void>; busy: boolean; payload: PlaylistImportPayload | null; onSave: () => Promise<void>; saving: boolean; assignments: Record<number, { user_id: string; notes: string }>; onAssignmentChange: (position: number, key: "user_id" | "notes", value: string) => void; lockSubmissions: boolean; onToggleLock: () => void; statusMessage: string | null }) {
  const [playlistRef, setPlaylistRef] = useState("");
  const [playlistMonth, setPlaylistMonth] = useState(() => {
    const now = new Date();
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
  });
  const [error, setError] = useState<string | null>(null);

  const handleImport = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    try {
      await onImport(playlistRef.trim(), playlistMonth);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unable to load playlist";
      setError(message);
    }
  };

  return (
    <section className="card">
      <div className="card__header">
        <h2>Backfill Spotify Playlist</h2>
      </div>
      <p className="muted">Import an existing Spotify playlist and optionally assign each track to a crew member.</p>
      <form className="import-form" onSubmit={handleImport}>
        <div className="field">
          <label>Spotify playlist link or ID</label>
          <input value={playlistRef} onChange={(event) => setPlaylistRef(event.target.value)} placeholder="https://open.spotify.com/playlist/..." required />
        </div>
        <div className="field">
          <label>Playlist month</label>
          <input type="month" value={playlistMonth} onChange={(event) => setPlaylistMonth(event.target.value)} required />
        </div>
        <button className="primary" type="submit" disabled={busy}>
          {busy ? "Loading…" : "Fetch playlist"}
        </button>
      </form>
      {error && <p className="error">{error}</p>}
      {statusMessage && <p className="success">{statusMessage}</p>}

      {payload && (
        <div className="import-preview">
          <header>
            <h3>{payload.name}</h3>
            <p className="muted">{payload.tracks.length} tracks · {payload.playlist_month}</p>
            {payload.description && <p className="muted small">{payload.description}</p>}
          </header>
          <div className="import-table">
            <div className="import-table__row import-table__row--head">
              <span>#</span>
              <span>Track</span>
              <span>Assign to</span>
              <span>Notes</span>
            </div>
            {payload.tracks.map((track) => (
              <div className="import-table__row" key={`${track.spotify_track_id}-${track.position}`}>
                <span>{track.position}</span>
                <div>
                  <p className="strong">{track.name}</p>
                  <p className="muted small">{track.artists || track.artist}</p>
                </div>
                <select value={assignments[track.position]?.user_id ?? ""} onChange={(event) => onAssignmentChange(track.position, "user_id", event.target.value)}>
                  <option value="">—</option>
                  {users.map((member) => (
                    <option key={member.id} value={String(member.id)}>
                      {member.display_name?.trim() || member.username}
                    </option>
                  ))}
                </select>
                <input value={assignments[track.position]?.notes ?? ""} onChange={(event) => onAssignmentChange(track.position, "notes", event.target.value)} placeholder="Notes" />
              </div>
            ))}
          </div>
          <div className="import-actions">
            <label className="toggle">
              <input type="checkbox" checked={lockSubmissions} onChange={onToggleLock} />
              <span>Lock submissions for assigned tracks</span>
            </label>
            <button className="primary" onClick={onSave} disabled={saving}>
              {saving ? "Saving…" : "Save playlist"}
            </button>
          </div>
        </div>
      )}
    </section>
  );
}

type FetchOptions<T> = RequestInit & { parse?: (value: any) => T };

async function fetchJson<T>(input: RequestInfo, init?: FetchOptions<T>) {
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

  if (response.status === 204) {
    return undefined as T;
  }

  const data = await response.json();
  return init?.parse ? init.parse(data) : (data as T);
}

function startOfCurrentMonthIso(): string {
  const now = new Date();
  const monthStart = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), 1, 0, 0, 0));
  return monthStart.toISOString();
}

export function App() {
  const [authState, setAuthState] = useState<AuthState>("loading");
  const [authError, setAuthError] = useState<string | null>(null);
  const [user, setUser] = useState<UserSummary | null>(null);
  const [users, setUsers] = useState<UserSummary[]>([]);
  const [activeView, setActiveView] = useState<AppView>("submit");
  const [loginInFlight, setLoginInFlight] = useState(false);

  const [submission, setSubmission] = useState<SubmissionRecord | null>(null);
  const [submissionLoading, setSubmissionLoading] = useState(false);
  const [submissionNotes, setSubmissionNotes] = useState("");
  const [submissionMessage, setSubmissionMessage] = useState<string | null>(null);
  const [submissionError, setSubmissionError] = useState<string | null>(null);

  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<SpotifyTrackResult[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);

  const [historyList, setHistoryList] = useState<PlaylistRecord[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [selectedPlaylist, setSelectedPlaylist] = useState<PlaylistRecord | null>(null);
  const [playlistDetailLoading, setPlaylistDetailLoading] = useState(false);
  const [playlistDetailError, setPlaylistDetailError] = useState<string | null>(null);

  const [lookupQuery, setLookupQuery] = useState("");
  const [lookupResults, setLookupResults] = useState<SpotifyTrackResult[]>([]);
  const [lookupLoading, setLookupLoading] = useState(false);
  const [lookupError, setLookupError] = useState<string | null>(null);

  const [invites, setInvites] = useState<InviteRecord[]>([]);
  const [inviteBusy, setInviteBusy] = useState(false);

  const [importBusy, setImportBusy] = useState(false);
  const [importPayload, setImportPayload] = useState<PlaylistImportPayload | null>(null);
  const [importSaving, setImportSaving] = useState(false);
  const [importAssignments, setImportAssignments] = useState<Record<number, { user_id: string; notes: string }>>({});
  const [importLock, setImportLock] = useState(true);
  const [importStatus, setImportStatus] = useState<string | null>(null);

  const currentMonthIso = useMemo(() => startOfCurrentMonthIso(), []);

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

  const loadUsers = useCallback(async () => {
    if (!user || user.role !== "admin") {
      setUsers([]);
      return;
    }
    try {
      const payload = await fetchJson<{ items: UserSummary[] }>("/api/v1/users");
      setUsers(payload.items);
    } catch (error) {
      console.error("Failed to load users", error);
      setUsers([]);
    }
  }, [user]);

  const loadSubmission = useCallback(async () => {
    setSubmissionLoading(true);
    setSubmissionError(null);
    try {
      const payload = await fetchJson<{ items: SubmissionRecord[] }>(`/api/v1/submissions?month=${encodeURIComponent(currentMonthIso)}`);
      const record = payload.items[0] ?? null;
      setSubmission(record);
      setSubmissionNotes(record?.notes ?? "");
    } catch (error) {
      console.error("Failed to load submission", error);
      setSubmissionError("Unable to load submission. Try again shortly.");
      setSubmission(null);
    } finally {
      setSubmissionLoading(false);
    }
  }, [currentMonthIso]);

  const loadPlaylistDetail = useCallback(async (playlistId: number) => {
    setPlaylistDetailLoading(true);
    setPlaylistDetailError(null);
    try {
      const payload = await fetchJson<PlaylistRecord>(`/api/v1/playlists/${playlistId}`);
      setSelectedPlaylist(payload);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unable to load playlist";
      setPlaylistDetailError(message);
      setSelectedPlaylist(null);
    } finally {
      setPlaylistDetailLoading(false);
    }
  }, []);

  const loadHistoryList = useCallback(async () => {
    setHistoryLoading(true);
    try {
      const payload = await fetchJson<{ items: PlaylistRecord[] }>("/api/v1/playlists");
      setHistoryList(payload.items);
      if (payload.items.length > 0) {
        await loadPlaylistDetail(payload.items[0].id);
      } else {
        setSelectedPlaylist(null);
      }
    } catch (error) {
      console.error("Failed to load playlists", error);
      setHistoryList([]);
      setSelectedPlaylist(null);
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  const loadInvites = useCallback(async () => {
    if (!user || user.role !== "admin") {
      setInvites([]);
      return;
    }
    setInviteBusy(true);
    try {
      const payload = await fetchJson<{ items: InviteRecord[] }>("/api/v1/admin/invites");
      setInvites(payload.items);
    } catch (error) {
      console.error("Failed to fetch invites", error);
    } finally {
      setInviteBusy(false);
    }
  }, [user]);

  useEffect(() => {
    loadUser();
  }, [loadUser]);

  useEffect(() => {
    if (authState === "authenticated") {
      loadUsers();
    }
  }, [authState, loadUsers]);

  useEffect(() => {
    if (authState !== "authenticated") {
      setSubmission(null);
      setHistoryList([]);
      setSelectedPlaylist(null);
      setInvites([]);
      setImportPayload(null);
      setImportAssignments({});
      setImportStatus(null);
      return;
    }

    if (activeView === "submit") loadSubmission();
    if (activeView === "history") loadHistoryList();
    if (activeView === "admin" && user?.role === "admin") loadInvites();
  }, [authState, activeView, loadSubmission, loadHistoryList, loadInvites, user]);

  useEffect(() => {
    if (user?.role !== "admin" && activeView === "admin") {
      setActiveView("submit");
    }
  }, [user, activeView]);

  const startLogin = useCallback(async () => {
    setAuthError(null);
    setLoginInFlight(true);
    try {
      const redirect_to = window.location.href;
      const query = new URLSearchParams({ redirect_to });
      const payload = await fetchJson<{ authorization_url: string; state: string }>(`/api/v1/auth/login?${query.toString()}`);
      window.location.href = payload.authorization_url;
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unable to start login.";
      setAuthError(message);
      setLoginInFlight(false);
    }
  }, []);

  const logout = useCallback(async () => {
    try {
      await fetch("/api/v1/auth/logout", { method: "POST", credentials: "include" });
    } finally {
      setUser(null);
      setAuthState("unauthenticated");
      setSubmission(null);
      setHistoryList([]);
      setSelectedPlaylist(null);
      setInvites([]);
      setImportPayload(null);
      setImportAssignments({});
      setImportStatus(null);
      setActiveView("submit");
    }
  }, []);

  const selectTrack = useCallback(
    async (track: SpotifyTrackResult) => {
      setSubmissionError(null);
      setSubmissionMessage(null);
      try {
        await fetchJson(`/api/v1/submissions`, {
          method: "POST",
          body: JSON.stringify({
            submission_month: currentMonthIso,
            notes: submissionNotes.trim() ? submissionNotes.trim() : null,
            track: {
              spotify_track_id: track.spotify_track_id,
              name: track.name,
              artist: track.artist,
              album: track.album ?? null,
              duration_ms: track.duration_ms ?? null,
              spotify_url: track.spotify_url ?? null,
              genres: [],
              lastfm_tags: [],
            },
          }),
        });
        setSubmissionMessage("Submission saved!");
        setSearchResults([]);
        await loadSubmission();
      } catch (error) {
        const message = error instanceof Error ? error.message : "Unable to save submission";
        setSubmissionError(message);
      }
    },
    [currentMonthIso, loadSubmission, submissionNotes]
  );

  const searchTracks = useCallback(async () => {
    if (!searchQuery.trim()) return;
    setSearchLoading(true);
    try {
      const payload = await fetchJson<SpotifyTrackResult[]>(`/api/v1/tracks/search?query=${encodeURIComponent(searchQuery.trim())}&limit=10`);
      setSearchResults(payload);
    } catch (error) {
      console.error("Track search failed", error);
      setSubmissionError("Unable to search Spotify right now.");
    } finally {
      setSearchLoading(false);
    }
  }, [searchQuery]);

  const lookupTracks = useCallback(async () => {
    setLookupError(null);
    if (!lookupQuery.trim()) {
      setLookupResults([]);
      return;
    }
    setLookupLoading(true);
    try {
      const payload = await fetchJson<SpotifyTrackResult[]>(`/api/v1/tracks/search?query=${encodeURIComponent(lookupQuery.trim())}&limit=15`);
      setLookupResults(payload);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Lookup failed";
      setLookupError(message);
      setLookupResults([]);
    } finally {
      setLookupLoading(false);
    }
  }, [lookupQuery]);

  const createInvite = useCallback<InviteForm["props"]["onCreate"]>(
    async ({ email, role, expires_in_days }) => {
      setInviteBusy(true);
      try {
        await fetchJson(`/api/v1/admin/invites`, {
          method: "POST",
          body: JSON.stringify({ email, role, expires_in_days }),
        });
        await loadInvites();
      } finally {
        setInviteBusy(false);
      }
    },
    [loadInvites]
  );

  const importPlaylist = useCallback(async (playlistRef: string, playlistMonth: string) => {
    setImportBusy(true);
    setImportPayload(null);
    setImportAssignments({});
    setImportStatus(null);
    try {
      const payload = await fetchJson<PlaylistImportPayload>("/api/v1/playlists/import", {
        method: "POST",
        body: JSON.stringify({ playlist_ref: playlistRef, playlist_month: playlistMonth }),
      });
      setImportPayload(payload);
      setImportLock(true);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unable to load playlist";
      setImportStatus(message);
    } finally {
      setImportBusy(false);
    }
  }, []);

  const saveImport = useCallback(async () => {
    if (!importPayload) return;
    setImportSaving(true);
    setImportStatus(null);
    try {
      const assignments = Object.entries(importAssignments)
        .filter(([position]) => Number(position) > 0)
        .map(([position, data]) => ({
          position: Number(position),
          user_id: data.user_id ? Number(data.user_id) : undefined,
          notes: data.notes || undefined,
        }));

      await fetchJson("/api/v1/playlists/import/save", {
        method: "POST",
        body: JSON.stringify({
          payload: importPayload,
          assignments,
          lock_submissions: importLock,
        }),
      });
      setImportPayload(null);
      setImportAssignments({});
      setImportStatus("Playlist saved successfully.");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unable to save playlist";
      setImportStatus(message);
    } finally {
      setImportSaving(false);
    }
  }, [importAssignments, importLock, importPayload]);

  const updateAssignment = useCallback(
    (position: number, key: "user_id" | "notes", value: string) => {
      setImportAssignments((prev) => ({
        ...prev,
        [position]: {
          user_id: key === "user_id" ? value : prev[position]?.user_id ?? "",
          notes: key === "notes" ? value : prev[position]?.notes ?? "",
        },
      }));
    },
    []
  );

  const toggleImportLock = useCallback(() => {
    setImportLock((prev) => !prev);
  }, []);

  const body = useMemo(() => {
    if (authState === "loading") {
      return (
        <section className="card auth">
          <p className="muted">Checking your session…</p>
        </section>
      );
    }

    if (authState === "unauthenticated") {
      return <LoginPage onLogin={startLogin} loading={loginInFlight} error={authError} />;
    }

    if (authState === "forbidden") {
      return <ForbiddenPage />;
    }

    if (!user) {
      return null;
    }

    if (activeView === "submit") {
      return (
        <SubmissionPanel
          submission={submission}
          isLoading={submissionLoading}
          isLocked={Boolean(submission?.is_locked)}
          notes={submissionNotes}
          onNotesChange={setSubmissionNotes}
          onSearch={searchTracks}
          searchQuery={searchQuery}
          onSearchQueryChange={setSearchQuery}
          searchResults={searchResults}
          searchLoading={searchLoading}
          onSelectTrack={selectTrack}
          message={submissionMessage}
          error={submissionError}
        />
      );
    }

    if (activeView === "history") {
      return (
        <HistoryView
          playlists={historyList}
          loading={historyLoading}
          onSelect={loadPlaylistDetail}
          selected={selectedPlaylist}
          detailLoading={playlistDetailLoading}
          detailError={playlistDetailError}
        />
      );
    }

    if (activeView === "lookup") {
      return (
        <LookupPanel
          query={lookupQuery}
          onQueryChange={setLookupQuery}
          onSearch={lookupTracks}
          loading={lookupLoading}
          results={lookupResults}
          error={lookupError}
        />
      );
    }

    if (activeView === "admin" && user.role === "admin") {
      return (
        <div className="admin-grid">
          <section className="card">
            <div className="card__header">
              <h2>Invites</h2>
            </div>
            <InviteForm onCreate={createInvite} busy={inviteBusy} />
            <InvitesPanel invites={invites} onRefresh={loadInvites} busy={inviteBusy} />
          </section>
          <AdminPlaylistImport
            users={users}
            onImport={importPlaylist}
            busy={importBusy}
            payload={importPayload}
            onSave={saveImport}
            saving={importSaving}
            assignments={importAssignments}
            onAssignmentChange={updateAssignment}
            lockSubmissions={importLock}
            onToggleLock={toggleImportLock}
            statusMessage={importStatus}
          />
        </div>
      );
    }

    return null;
  }, [
    activeView,
    authError,
    authState,
    createInvite,
    historyList,
    historyLoading,
    importAssignments,
    importBusy,
    importPayload,
    importLock,
    importPayload,
    importSaving,
    importStatus,
    inviteBusy,
    invites,
    loadInvites,
    loadPlaylistDetail,
    loginInFlight,
    lookupError,
    lookupLoading,
    lookupQuery,
    lookupResults,
    lookupTracks,
    saveImport,
    searchLoading,
    searchQuery,
    searchResults,
    searchTracks,
    selectTrack,
    selectedPlaylist,
    playlistDetailLoading,
    playlistDetailError,
    submission,
    submissionError,
    submissionLoading,
    submissionMessage,
    submissionNotes,
    toggleImportLock,
    updateAssignment,
    users,
    user
  ]);

  return (
    <>
      <style>{globalStyles}</style>
      <TopBar authState={authState} user={user} activeView={activeView} onSelectView={setActiveView} onLogin={startLogin} onLogout={logout} />
      <main className="layout">{body}</main>
    </>
  );
}

const globalStyles = `
  :root {
    color-scheme: dark light;
    font-family: "Inter", system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    background: radial-gradient(circle at top, #0b1120, #020617 50%, #000000 100%);
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

  button.small {
    padding: 0.45rem 1.1rem;
    border-radius: 0.65rem;
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

  .topbar {
    position: sticky;
    top: 0;
    z-index: 10;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1.5rem;
    padding: 1rem 2.5rem;
    background: linear-gradient(90deg, rgba(15, 23, 42, 0.9), rgba(15, 23, 42, 0.7));
    border-bottom: 1px solid rgba(148, 163, 184, 0.12);
    backdrop-filter: blur(12px);
  }

  .topbar__brand {
    font-weight: 700;
    letter-spacing: 0.04em;
  }

  .topbar__nav {
    display: flex;
    gap: 0.75rem;
    flex-wrap: wrap;
  }

  .topbar__pill {
    padding: 0.45rem 1rem;
    border-radius: 999px;
    background: rgba(30, 41, 59, 0.7);
    font-size: 0.85rem;
    color: rgba(226, 232, 240, 0.82);
  }

  .topbar__pill--active {
    background: linear-gradient(135deg, rgba(34, 211, 238, 0.8), rgba(99, 102, 241, 0.8));
    color: #0f172a;
  }

  .topbar__pill:disabled {
    opacity: 0.35;
    cursor: not-allowed;
  }

  .topbar__auth {
    display: flex;
    align-items: center;
    gap: 0.75rem;
  }

  .topbar__user {
    font-weight: 600;
  }

  .layout {
    padding: 2.5rem 3rem 4rem;
    min-height: calc(100vh - 72px);
    display: flex;
    justify-content: center;
  }

  .layout > * {
    width: min(1100px, 100%);
  }

  .card {
    background: rgba(15, 23, 42, 0.82);
    border: 1px solid rgba(148, 163, 184, 0.2);
    border-radius: 1.25rem;
    padding: 1.9rem 2.2rem;
    box-shadow: 0 25px 60px rgba(15, 23, 42, 0.45);
  }

  .card.auth {
    width: min(440px, 100%);
    margin: 4rem auto 0;
    text-align: center;
  }

  .card__header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    margin-bottom: 1rem;
  }

  .field {
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
    margin-top: 0.9rem;
  }

  .field:first-of-type {
    margin-top: 0;
  }

  .field-row {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    margin-top: 0.9rem;
  }

  .field-row label {
    font-weight: 600;
  }

  .invite-button {
    margin-top: 0.9rem;
    width: fit-content;
  }

  textarea, input, select {
    background: rgba(15, 23, 42, 0.6);
    border: 1px solid rgba(148, 163, 184, 0.25);
    border-radius: 0.75rem;
    padding: 0.6rem 0.85rem;
    color: #e2e8f0;
    width: 100%;
  }

  textarea {
    resize: vertical;
    min-height: 120px;
  }

  textarea:focus, input:focus, select:focus {
    outline: 2px solid rgba(94, 234, 212, 0.45);
    border-color: transparent;
  }

  .submission-status {
    margin: 1.5rem 0;
  }

  .submission-card {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 1.5rem;
    padding: 1.35rem 1.6rem;
    border-radius: 1rem;
    background: rgba(30, 41, 59, 0.65);
  }

  .submission-search,
  .lookup-form {
    display: flex;
    gap: 1rem;
    margin: 1.5rem 0 0.5rem;
    align-items: flex-end;
    flex-wrap: wrap;
  }

  .submission-search .field,
  .lookup-form .field {
    flex: 1 1 240px;
    margin-top: 0;
  }

  .search-results {
    margin-top: 1.25rem;
    display: grid;
    gap: 0.75rem;
  }

  .result {
    width: 100%;
    display: flex;
    justify-content: space-between;
    align-items: center;
    text-align: left;
    padding: 1rem 1.25rem;
    border-radius: 1rem;
    background: rgba(30, 41, 59, 0.65);
  }

  .result--static {
    cursor: default;
  }

  .result h4 {
    margin-bottom: 0.4rem;
  }

  .pill {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 0.25rem 0.7rem;
    border-radius: 999px;
    background: rgba(59, 130, 246, 0.25);
    color: rgba(191, 219, 254, 0.95);
    font-size: 0.8rem;
  }

  .pill--cta {
    background: rgba(94, 234, 212, 0.3);
    color: rgba(224, 255, 251, 0.95);
  }

  .pill--admin {
    background: rgba(34, 197, 94, 0.25);
    color: rgba(220, 252, 231, 0.95);
  }

  .pill--spotify {
    background: rgba(34, 197, 94, 0.25);
    color: rgba(187, 247, 208, 0.95);
  }

  .pill--locked {
    background: rgba(248, 113, 113, 0.25);
    color: rgba(254, 226, 226, 0.95);
  }

  .link {
    color: rgba(94, 234, 212, 0.95);
  }

  .history-shell {
    display: grid;
    grid-template-columns: minmax(220px, 260px) 1fr;
    gap: 1.5rem;
  }

  .history-list {
    background: rgba(15, 23, 42, 0.6);
    border: 1px solid rgba(148, 163, 184, 0.15);
    border-radius: 1.1rem;
    padding: 1.2rem;
    display: grid;
    gap: 0.6rem;
    height: fit-content;
  }

  .history-list__item {
    background: transparent;
    border: 0;
    text-align: left;
    border-radius: 0.8rem;
    padding: 0.65rem 0.8rem;
    color: rgba(226, 232, 240, 0.85);
    display: flex;
    flex-direction: column;
  }

  .history-list__item--active {
    background: rgba(59, 130, 246, 0.2);
    color: #e2e8f0;
  }

  .history-detail {
    min-height: 320px;
  }

  .tracklist {
    list-style: none;
    padding: 0;
    margin: 1.2rem 0 0;
    display: grid;
    gap: 0.6rem;
  }

  .tracklist__item {
    display: flex;
    justify-content: space-between;
    gap: 1rem;
    flex-wrap: wrap;
    background: rgba(15, 23, 42, 0.55);
    border-radius: 0.9rem;
    padding: 0.75rem 0.9rem;
  }

  .tracklist__left {
    display: grid;
    gap: 0.25rem;
  }

  .tracklist__title {
    font-weight: 600;
  }

  .tracklist__meta {
    color: rgba(148, 163, 184, 0.85);
  }

  .tracklist__right {
    display: flex;
    align-items: center;
    gap: 0.75rem;
  }

  .tracklist__duration {
    color: rgba(148, 163, 184, 0.75);
  }

  .tracklist__submitter {
    color: rgba(148, 163, 184, 0.65);
  }

  .admin-grid {
    display: grid;
    gap: 2rem;
  }

  .table {
    display: grid;
    gap: 0.5rem;
  }

  .table__row {
    display: grid;
    grid-template-columns: 2fr 2fr 1fr 2fr;
    gap: 0.75rem;
    align-items: center;
    padding: 0.75rem;
    border-radius: 0.9rem;
    background: rgba(15, 23, 42, 0.65);
  }

  .table__row--head {
    font-weight: 600;
    color: rgba(148, 163, 184, 0.8);
    background: transparent;
    padding-bottom: 0.25rem;
  }

  .token {
    font-family: "JetBrains Mono", "SFMono-Regular", Menlo, monospace;
    font-size: 0.85rem;
  }

  .import-form {
    display: grid;
    gap: 1rem;
    margin-bottom: 1.25rem;
  }

  .import-preview header {
    margin-bottom: 1rem;
  }

  .import-table {
    display: grid;
    gap: 0.6rem;
  }

  .import-table__row {
    display: grid;
    grid-template-columns: 50px 2fr 1fr 1fr;
    gap: 0.75rem;
    align-items: center;
    padding: 0.75rem;
    border-radius: 0.9rem;
    background: rgba(15, 23, 42, 0.6);
  }

  .import-table__row--head {
    font-weight: 600;
    color: rgba(148, 163, 184, 0.8);
    background: transparent;
  }

  .import-actions {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    margin-top: 1.5rem;
    flex-wrap: wrap;
  }

  .toggle {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.9rem;
  }

  @media (max-width: 960px) {
    .history-shell {
      grid-template-columns: 1fr;
    }

    .import-table__row,
    .table__row {
      grid-template-columns: repeat(2, 1fr);
    }
  }

  @media (max-width: 780px) {
    .topbar {
      flex-wrap: wrap;
      padding: 1rem 1.5rem;
    }

    .layout {
      padding: 1.5rem;
    }

    .card {
      padding: 1.6rem;
    }

    .import-actions {
      flex-direction: column;
      align-items: flex-start;
    }
  }

`

export default App;
