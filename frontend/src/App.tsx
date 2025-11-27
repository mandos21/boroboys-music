import { useCallback, useEffect, useMemo, useState } from "react";
import AdminMonthPanel from "./components/AdminMonthPanel";
import AdminPlaylistImport from "./components/AdminPlaylistImport";
import ForbiddenPage from "./components/ForbiddenPage";
import HistoryView from "./components/HistoryView";
import InviteForm from "./components/InviteForm";
import InvitesPanel from "./components/InvitesPanel";
import LoginPage from "./components/LoginPage";
import LookupPanel from "./components/LookupPanel";
import SubmissionPanel from "./components/SubmissionPanel";
import TopBar from "./components/TopBar";
import { fetchJson } from "./utils/api";
import { startOfCurrentMonthIso } from "./utils/date";
import type {
  AdminMonthSummary,
  AppView,
  AuthState,
  ImportAssignments,
  InviteRecord,
  PlaylistImportPayload,
  PlaylistRecord,
  Role,
  SpotifyTrackResult,
  SubmissionRecord,
  SubmissionLimitInfo,
  UserSummary,
} from "./types";
import "./styles.css";

const SPOTIFY_TRACK_PATTERN = /(?:https?:\/\/open\.spotify\.com\/track\/|spotify:track:)?([A-Za-z0-9]{22})/;

const extractSpotifyTrackId = (value: string): string | null => {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const match = SPOTIFY_TRACK_PATTERN.exec(trimmed);
  if (match?.[1]) {
    return match[1];
  }
  return trimmed.length === 22 && /^[A-Za-z0-9]+$/.test(trimmed) ? trimmed : null;
};

function App() {
  const [authState, setAuthState] = useState<AuthState>("loading");
  const [authError, setAuthError] = useState<string | null>(null);
  const [user, setUser] = useState<UserSummary | null>(null);
  const [users, setUsers] = useState<UserSummary[]>([]);
  const [activeView, setActiveView] = useState<AppView>("submit");
  const [loginInFlight, setLoginInFlight] = useState(false);

  const [submissions, setSubmissions] = useState<SubmissionRecord[]>([]);
  const [submissionLoading, setSubmissionLoading] = useState(false);
  const [submissionNotes, setSubmissionNotes] = useState("");
  const [submissionMessage, setSubmissionMessage] = useState<string | null>(null);
  const [submissionError, setSubmissionError] = useState<string | null>(null);
  const [submissionLimit, setSubmissionLimit] = useState<number | null>(null);
  const [submissionsLocked, setSubmissionsLocked] = useState(false);

  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<SpotifyTrackResult[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [resolveLoading, setResolveLoading] = useState(false);

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
  const [importAssignments, setImportAssignments] = useState<ImportAssignments>({});
  const [importLock, setImportLock] = useState(true);
  const [importStatus, setImportStatus] = useState<string | null>(null);

  const [monthSummary, setMonthSummary] = useState<AdminMonthSummary | null>(null);
  const [monthSummaryLoading, setMonthSummaryLoading] = useState(false);
  const [monthSummaryError, setMonthSummaryError] = useState<string | null>(null);
  const [monthSettingsSaving, setMonthSettingsSaving] = useState(false);
  const [releaseBusy, setReleaseBusy] = useState(false);
  const [monthStatusMessage, setMonthStatusMessage] = useState<string | null>(null);
  const [monthStatusError, setMonthStatusError] = useState<string | null>(null);

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

  const loadSubmissionLimit = useCallback(async () => {
    try {
      const payload = await fetchJson<SubmissionLimitInfo>(
        `/api/v1/submissions/limit/current?month=${encodeURIComponent(currentMonthIso)}`
      );
      setSubmissionLimit(payload.submission_limit);
      setSubmissionsLocked(payload.is_locked);
    } catch (error) {
      console.error("Failed to load submission limit", error);
      setSubmissionLimit(null);
    }
  }, [currentMonthIso]);

  const loadSubmissions = useCallback(async () => {
    setSubmissionLoading(true);
    setSubmissionError(null);
    try {
      const payload = await fetchJson<{ items: SubmissionRecord[] }>(`/api/v1/submissions?month=${encodeURIComponent(currentMonthIso)}`);
      setSubmissions(payload.items);
      setSubmissionNotes("");
      setSubmissionsLocked(payload.items.some((item) => item.is_locked));
    } catch (error) {
      console.error("Failed to load submission", error);
      setSubmissionError("Unable to load submission. Try again shortly.");
      setSubmissions([]);
      setSubmissionsLocked(false);
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
  }, [loadPlaylistDetail]);

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

  const loadMonthSummary = useCallback(async () => {
    setMonthSummaryLoading(true);
    setMonthSummaryError(null);
    try {
      const payload = await fetchJson<AdminMonthSummary>("/api/v1/admin/months/current");
      setMonthSummary(payload);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unable to load month overview.";
      setMonthSummaryError(message);
      setMonthSummary(null);
    } finally {
      setMonthSummaryLoading(false);
    }
  }, []);

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
      setSubmissions([]);
      setSubmissionLimit(null);
      setSubmissionsLocked(false);
      setHistoryList([]);
      setSelectedPlaylist(null);
      setInvites([]);
      setImportPayload(null);
      setImportAssignments({});
      setImportStatus(null);
      setMonthSummary(null);
      setMonthSummaryError(null);
      setMonthStatusMessage(null);
      setMonthStatusError(null);
      return;
    }

    if (activeView === "submit") {
      loadSubmissions();
      loadSubmissionLimit();
    }
    if (activeView === "history") loadHistoryList();
    if (activeView === "admin" && user?.role === "admin") {
      loadInvites();
      loadMonthSummary();
    }
  }, [activeView, authState, loadHistoryList, loadInvites, loadMonthSummary, loadSubmissionLimit, loadSubmissions, user]);

  useEffect(() => {
    if (user?.role !== "admin" && activeView === "admin") {
      setActiveView("submit");
    }
  }, [activeView, user]);

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
      setSubmissions([]);
      setHistoryList([]);
      setSelectedPlaylist(null);
      setInvites([]);
      setImportPayload(null);
      setImportAssignments({});
      setImportStatus(null);
      setSubmissionLimit(null);
      setSubmissionsLocked(false);
      setSubmissionNotes("");
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
              artwork_url: track.artwork_url ?? null,
              genres: [],
              lastfm_tags: [],
            },
          }),
        });
        setSubmissionMessage("Submission saved!");
        setSearchResults([]);
        setSearchQuery("");
        setSubmissionNotes("");
        await Promise.all([loadSubmissions(), loadSubmissionLimit()]);
      } catch (error) {
        const message = error instanceof Error ? error.message : "Unable to save submission";
        setSubmissionError(message);
      }
    },
    [currentMonthIso, loadSubmissionLimit, loadSubmissions, submissionNotes]
  );

  const resolveTrackReference = useCallback(
    async (reference: string) => {
      const trimmed = reference.trim();
      if (!trimmed) return;
      setSubmissionError(null);
      setSubmissionMessage(null);
      setSearchResults([]);
      setResolveLoading(true);
      try {
        const payload = await fetchJson<SpotifyTrackResult>(
          `/api/v1/tracks/resolve?ref=${encodeURIComponent(trimmed)}`
        );
        await selectTrack(payload);
      } catch (error) {
        const message = error instanceof Error ? error.message : "Unable to load track from Spotify.";
        setSubmissionError(message);
      } finally {
        setResolveLoading(false);
      }
    },
    [selectTrack]
  );

  const deleteSubmission = useCallback(
    async (submissionId: number) => {
      setSubmissionError(null);
      setSubmissionMessage(null);
      try {
        await fetchJson(`/api/v1/submissions/${submissionId}`, {
          method: "DELETE",
        });
        setSubmissionMessage("Submission removed.");
        await Promise.all([loadSubmissions(), loadSubmissionLimit()]);
      } catch (error) {
        const message = error instanceof Error ? error.message : "Unable to remove submission.";
        setSubmissionError(message);
      }
    },
    [loadSubmissionLimit, loadSubmissions]
  );

  const searchTracks = useCallback(async () => {
    const trimmedQuery = searchQuery.trim();
    if (!trimmedQuery) return;

    const possibleTrackId = extractSpotifyTrackId(trimmedQuery);
    if (possibleTrackId) {
      await resolveTrackReference(trimmedQuery);
      return;
    }

    setSearchLoading(true);
    try {
      const payload = await fetchJson<SpotifyTrackResult[]>(
        `/api/v1/tracks/search?query=${encodeURIComponent(trimmedQuery)}&limit=10`
      );
      setSearchResults(payload);
    } catch (error) {
      console.error("Track search failed", error);
      setSubmissionError("Unable to search Spotify right now.");
    } finally {
      setSearchLoading(false);
    }
  }, [resolveTrackReference, searchQuery]);


  const updateMonthSettings = useCallback(
    async ({ submission_limit, spotify_owner_id }: { submission_limit: number | null; spotify_owner_id: string | null }) => {
      setMonthSettingsSaving(true);
      setMonthStatusMessage(null);
      setMonthStatusError(null);
      try {
        await fetchJson("/api/v1/admin/months/current", {
          method: "PUT",
          body: JSON.stringify({ submission_limit, spotify_owner_id }),
        });
        setMonthStatusMessage("Settings updated.");
        await loadMonthSummary();
      } catch (error) {
        const message = error instanceof Error ? error.message : "Unable to update month settings.";
        setMonthStatusError(message);
      } finally {
        setMonthSettingsSaving(false);
      }
    },
    [loadMonthSummary]
  );

  const releaseCurrentMonth = useCallback(async () => {
    setReleaseBusy(true);
    setMonthStatusMessage(null);
    setMonthStatusError(null);
    try {
      await fetchJson<PlaylistRecord>("/api/v1/admin/months/release", {
        method: "POST",
        body: JSON.stringify({}),
      });
      setMonthStatusMessage("Playlist released.");
      await loadMonthSummary();
      await loadHistoryList();
      await Promise.all([loadSubmissions(), loadSubmissionLimit()]);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unable to release the playlist.";
      setMonthStatusError(message);
    } finally {
      setReleaseBusy(false);
    }
  }, [loadHistoryList, loadMonthSummary, loadSubmissionLimit, loadSubmissions]);

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

  const createInvite = useCallback(
    async ({ email, role, expires_in_days }: { email?: string | null; role: Role; expires_in_days: number }) => {
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

  const updateAssignment = useCallback((position: number, key: "user_id" | "notes", value: string) => {
    setImportAssignments((prev) => ({
      ...prev,
      [position]: {
        user_id: key === "user_id" ? value : prev[position]?.user_id ?? "",
        notes: key === "notes" ? value : prev[position]?.notes ?? "",
      },
    }));
  }, []);

  const toggleImportLock = useCallback(() => {
    setImportLock((prev) => !prev);
  }, []);

  const submissionsUsed = submissions.length;
  const submissionsRemaining =
    submissionLimit == null ? null : Math.max(submissionLimit - submissionsUsed, 0);

  let content: JSX.Element | null = null;

  if (authState === "loading") {
    content = (
      <section className="card auth">
        <p className="muted">Checking your session…</p>
      </section>
    );
  } else if (authState === "unauthenticated") {
    content = <LoginPage onLogin={startLogin} loading={loginInFlight} error={authError} />;
  } else if (authState === "forbidden") {
    content = <ForbiddenPage />;
  } else if (!user) {
    content = null;
  } else if (activeView === "submit") {
    content = (
      <SubmissionPanel
        submissions={submissions}
        isLoading={submissionLoading}
        isLocked={submissionsLocked}
        limit={submissionLimit}
        used={submissionsUsed}
        remaining={submissionsRemaining}
        notes={submissionNotes}
        onNotesChange={setSubmissionNotes}
        onSearch={searchTracks}
        searchQuery={searchQuery}
        onSearchQueryChange={setSearchQuery}
        searchResults={searchResults}
        searchLoading={searchLoading}
        resolveLoading={resolveLoading}
        onSelectTrack={selectTrack}
        onDeleteSubmission={deleteSubmission}
        message={submissionMessage}
        error={submissionError}
      />
    );
  } else if (activeView === "history") {
    content = (
      <HistoryView
        playlists={historyList}
        loading={historyLoading}
        onSelect={loadPlaylistDetail}
        selected={selectedPlaylist}
        detailLoading={playlistDetailLoading}
        detailError={playlistDetailError}
      />
    );
  } else if (activeView === "lookup") {
    content = (
      <LookupPanel
        query={lookupQuery}
        onQueryChange={setLookupQuery}
        onSearch={lookupTracks}
        loading={lookupLoading}
        results={lookupResults}
        error={lookupError}
      />
    );
  } else if (activeView === "admin" && user.role === "admin") {
    content = (
      <div className="admin-grid">
        <AdminMonthPanel
          summary={monthSummary}
          loading={monthSummaryLoading}
          error={monthSummaryError}
          onUpdateSettings={updateMonthSettings}
          settingsSaving={monthSettingsSaving}
          releaseBusy={releaseBusy}
          onRelease={releaseCurrentMonth}
          statusMessage={monthStatusMessage}
          statusError={monthStatusError}
          users={users}
        />
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

  return (
    <>
      <TopBar authState={authState} user={user} activeView={activeView} onSelectView={setActiveView} onLogin={startLogin} onLogout={logout} />
      <main className="layout">{content}</main>
    </>
  );
}

export default App;
