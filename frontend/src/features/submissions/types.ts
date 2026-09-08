import type { components } from "../../api/schema";

export type Round = components["schemas"]["RoundDetailResponse"];
export type Track = components["schemas"]["TrackResponse"];
export type PolicyResult = components["schemas"]["PolicyResultResponse"];
export type Evaluation = components["schemas"]["TrackEvaluationResponse"];
export type Evidence = components["schemas"]["EvidenceResponse"];
export type Submission = components["schemas"]["SubmissionResponse"];
export type SubmissionResult = components["schemas"]["SubmissionResultResponse"];

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
    provider_metadata: track.providerMetadata ?? {},
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
