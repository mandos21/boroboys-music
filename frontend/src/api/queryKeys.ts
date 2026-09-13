/** Every query key in one place, so invalidation is greppable by symbol.
 *
 * A mistyped key used to fail silently as a cache miss; here it is a type
 * error. Shared prefixes are deliberate: invalidating `series()` also
 * invalidates `seriesDetail(id)`, because React Query matches keys by prefix.
 */
export const queryKeys = {
  session: () => ["session"] as const,
  connections: () => ["connections"] as const,
  profile: (userId?: string) => ["profile", userId ?? "me"] as const,
  notificationSettings: () => ["notification-settings"] as const,

  series: () => ["series"] as const,
  seriesDetail: (seriesId: string | undefined) => ["series", seriesId] as const,
  seriesInsights: (seriesId: string | undefined) => ["series", seriesId, "insights"] as const,
  seriesMembers: (seriesId: string | undefined) => ["series-members", seriesId] as const,
  seriesUsers: (seriesId: string | undefined, query: string) =>
    ["series-users", seriesId, query] as const,

  round: (roundId: string | undefined) => ["round", roundId] as const,
  roundSubmissions: (roundId: string | undefined) => ["round-submissions", roundId] as const,
  roundSubmissionCounts: (roundId: string | undefined) =>
    ["round-submission-counts", roundId] as const,
  roundUsers: (seriesId: string | undefined, query: string) =>
    ["round-users", seriesId, query] as const,
  submissionDraft: (roundId: string | undefined) => ["submission-draft", roundId] as const,
  listeningSuggestions: (roundId: string | undefined) =>
    ["listening-suggestions", roundId] as const,
  trackSearch: (roundId: string | undefined, query: string) =>
    ["track-search", roundId, query] as const,
  evidence: (roundId: string | undefined, trackId: string | undefined) =>
    ["evidence", roundId, trackId] as const,

  adminSeries: () => ["admin-series"] as const,
  adminSeriesDetail: (seriesId: string | undefined) => ["admin-series", seriesId] as const,
  adminRound: (roundId: string | undefined) => ["admin-round", roundId] as const,
  publication: (roundId: string) => ["publication", roundId] as const,
} as const;
