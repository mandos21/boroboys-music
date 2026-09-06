export type Session = { user: { platformRole: string } };

export type Series = {
  id: string;
  name: string;
  slug: string;
  description: string | null;
  timezone: string;
  defaultPolicies: Record<string, unknown>[];
  roundPlan: Record<string, unknown> | null;
  autoStartNextRound: boolean;
  isArchived: boolean;
};

export type User = {
  id: string;
  displayName: string | null;
  email: string | null;
};

export type Group = {
  id: string;
  name: string;
  description: string | null;
  memberCount: number;
  members: User[];
};

export type Round = {
  id: string;
  title: string;
  status: string;
  opensAt: string;
  closesAt: string;
  publishAt: string;
  submissionLimit: number;
};

export type SeriesDetail = Series & { groups: Group[]; rounds: Round[] };
export type RoundMember = User & {
  submissionLimitOverride: number | null;
  removedAt: string | null;
};
export type AdminRound = Round & {
  seriesId: string;
  timezone: string;
  policySnapshot: Record<string, unknown>[];
  members: RoundMember[];
};
export type Connection = {
  id: string;
  provider: string;
  displayName: string | null;
  isActive: boolean;
};
export type Publication = {
  id: string;
  state: string;
  isImported: boolean;
  retirementRequested: boolean;
  spotifyPlaylistId: string | null;
  attemptCount: number;
  lastError: string | null;
  publishedAt: string | null;
  unpublishedAt: string | null;
  events: Array<{ id: string; action: string; createdAt: string }>;
};
