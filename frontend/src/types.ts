export type AuthState = "loading" | "unauthenticated" | "authenticated" | "forbidden";

export type Role = "member" | "admin";

export type AppView = "submit" | "history" | "lookup" | "admin";

export type UserSummary = {
  id: number;
  username: string;
  display_name?: string | null;
  role: Role;
  email?: string | null;
  spotify_avatar_url?: string | null;
};

export type InviteRecord = {
  id: number;
  token: string;
  email?: string | null;
  role: Role;
  expires_at?: string | null;
  created_at: string;
};

export type TrackRead = {
  id: number;
  spotify_track_id: string;
  name: string;
  artist: string;
  album?: string | null;
  duration_ms?: number | null;
  spotify_url?: string | null;
  artwork_url?: string | null;
};

export type SubmissionRecord = {
  id: number;
  user_id: number;
  submission_month: string;
  notes?: string | null;
  is_locked: boolean;
  track: TrackRead;
};

export type PlaylistTrack = {
  position: number;
  track: TrackRead;
  submitter_id?: number | null;
  submitter_name?: string | null;
  submitter_notes?: string | null;
  submitter_avatar_url?: string | null;
};

export type PlaylistRecord = {
  id: number;
  name: string;
  description?: string | null;
  month: string;
  spotify_playlist_id?: string | null;
  tracks: PlaylistTrack[];
};

export type SpotifyTrackResult = {
  spotify_track_id: string;
  name: string;
  artist: string;
  album?: string | null;
  duration_ms?: number | null;
  spotify_url?: string | null;
  artwork_url?: string | null;
};

export type PlaylistImportTrack = SpotifyTrackResult & {
  position: number;
  artists?: string | null;
};

export type PlaylistImportPayload = {
  spotify_playlist_id: string;
  name: string;
  description?: string | null;
  playlist_month: string;
  snapshot_id?: string | null;
  tracks: PlaylistImportTrack[];
};

export type ImportAssignments = Record<number, { user_id: string; notes: string }>;

export type MonthSettings = {
  id: number;
  month: string;
  submission_limit?: number | null;
  spotify_owner_id?: string | null;
};

export type AdminMonthSummary = {
  settings: MonthSettings;
  submissions: SubmissionRecord[];
  released: boolean;
};
