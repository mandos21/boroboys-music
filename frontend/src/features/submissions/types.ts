import type { components } from "../../api/schema";

export type Round = {
  id: string;
  title: string;
  status: string;
  opensAt: string;
  closesAt: string;
  publishAt: string;
  submissionLimit: number;
  prompt: string | null;
  submittedCount: number;
  contributorCount: number;
};

export type Track = {
  spotifyTrackId: string;
  name: string;
  artist: string;
  album: string | null;
  spotifyUri: string | null;
  artworkUrl: string | null;
  providerMetadata: Record<string, unknown>;
};

export type PolicyResult = {
  kind: string;
  decision: "accept" | "warn" | "reject";
  message: string;
};

export type Evaluation = {
  trackId: string;
  canSubmit: boolean;
  limitRemaining: number;
  requiresWarningConfirmation: boolean;
  policyResults: PolicyResult[];
};

export type Evidence = {
  evidence: Array<{
    accountId: string;
    displayName: string | null;
    isMine: boolean;
    playcount: number | null;
    artistPlaycount: number | null;
    albumPlaycount: number | null;
    fetchedAt: string;
    refreshAfter: string | null;
    status: string;
  }>;
};

export type SubmissionResult = {
  accepted: boolean;
  id?: string;
  requiresWarningConfirmation?: boolean;
  policyResults: PolicyResult[];
};

export type TrackInput = components["schemas"]["TrackInput"];
export type TrackEvaluationRequest = components["schemas"]["TrackEvaluationRequest"];
export type SubmissionCreate = components["schemas"]["SubmissionCreate"];
export type SubmissionDraft = { track: TrackInput | null; note: string | null };

export function asTrackInput(track: Track): TrackInput {
  return {
    spotify_track_id: track.spotifyTrackId,
    name: track.name,
    artist: track.artist,
    album: track.album,
    spotify_uri: track.spotifyUri,
    artwork_url: track.artworkUrl,
    provider_metadata: track.providerMetadata,
  };
}

export function trackFromInput(track: TrackInput): Track {
  return {
    spotifyTrackId: track.spotify_track_id,
    name: track.name,
    artist: track.artist,
    album: track.album ?? null,
    spotifyUri: track.spotify_uri ?? null,
    artworkUrl: track.artwork_url ?? null,
    providerMetadata: track.provider_metadata ?? {},
  };
}
