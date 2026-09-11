import type { Page, Route } from "@playwright/test";

const ISO = "2026-09-10T16:00:00-04:00";

function artwork(color: string, label: string) {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="360" height="360" viewBox="0 0 360 360"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop stop-color="${color}"/><stop offset="1" stop-color="#101714"/></linearGradient></defs><rect width="360" height="360" fill="url(#g)"/><circle cx="274" cy="84" r="94" fill="#fff" fill-opacity=".14"/><path d="M0 246 360 144v216H0z" fill="#fff" fill-opacity=".09"/><text x="30" y="302" fill="#fff" font-family="system-ui,sans-serif" font-size="30" font-weight="800">${label}</text></svg>`;
  return `data:image/svg+xml;base64,${Buffer.from(svg).toString("base64")}`;
}

const art = [
  artwork("#15803d", "Night Drive"),
  artwork("#0f766e", "Lemonlight"),
  artwork("#7c3aed", "Northbound"),
  artwork("#b45309", "Slow Gold"),
  artwork("#be185d", "Velvet"),
  artwork("#0369a1", "Blue Hour"),
];

const groups = ["rock", "alternative", "electronic", "hip-hop", "pop", "jazz", "roots"];
const genreNames = [
  "art rock",
  "indie rock",
  "dream pop",
  "synthpop",
  "post-punk",
  "ambient",
  "indietronica",
  "alternative r&b",
  "neo-psychedelic",
  "shoegaze",
  "folk rock",
  "modern jazz",
  "chamber pop",
  "electropop",
  "garage rock",
  "trip hop",
  "new wave",
  "soul",
  "art pop",
  "experimental",
  "indie folk",
  "noise pop",
  "progressive rock",
  "soft rock",
  "dance pop",
  "minimalism",
  "singer-songwriter",
  "funk",
  "disco",
  "post-rock",
  "americana",
  "electronic rock",
];

const genres = genreNames.map((name, index) => ({
  name,
  group: groups[index % groups.length],
  count: Math.max(1, 18 - Math.floor(index / 2)),
}));

const contributors = [
  { id: "me", displayName: "Mara Green", spotifyProfileImageUrl: null, trackCount: 18 },
  { id: "riley", displayName: "Riley Ortega", spotifyProfileImageUrl: null, trackCount: 15 },
  { id: "shan", displayName: "Shan Patel", spotifyProfileImageUrl: null, trackCount: 12 },
  { id: "alex", displayName: "Alex Morgan", spotifyProfileImageUrl: null, trackCount: 10 },
].map((contributor, index) => ({
  ...contributor,
  genres: genres.filter((_, genreIndex) => genreIndex % 4 === index).slice(0, 10),
}));

const tracks = [
  ["Night Drive", "The Lanterns", "Slow Gold"],
  ["In the Rearview", "Marina Fields", "Northbound"],
  ["Lemonlight", "Pale Coast", "Lemonlight"],
  ["All the Way Home", "Isaac June", "Blue Hour"],
].map(([name, artist, album], index) => ({
  name,
  artist,
  album,
  artworkUrl: art[index],
  spotifyTrackId: `track-${index + 1}`,
  spotifyUri: `spotify:track:${index + 1}`,
}));

const submissions = tracks.map((track, index) => ({
  id: `submission-${index + 1}`,
  contributor: contributors[index],
  createdAt: ISO,
  updatedAt: ISO,
  withdrawnAt: null,
  isMine: index === 0,
  note: index === 0 ? "This one has been following me around all month." : null,
  status: "accepted",
  track,
}));

const openRound = {
  id: "round-open",
  seriesId: "series-1",
  title: "September after dark",
  status: "open",
  prompt: "Bring something that makes the late walk home better.",
  opensAt: "2026-09-01T00:00:00-04:00",
  closesAt: "2026-09-30T23:59:00-04:00",
  publishAt: "2026-10-01T09:00:00-04:00",
  submissionLimit: 3,
  submittedCount: 3,
  contributorCount: 4,
  canManage: true,
  isMember: true,
  spotifyPlaylistUrl: null,
  artworkUrls: art.slice(0, 4),
  backgroundArtworkUrl: art[0],
};

const publishedRound = {
  id: "round-august",
  title: "August favorites",
  status: "published",
  prompt: null,
  opensAt: "2026-08-01T00:00:00-04:00",
  closesAt: "2026-08-31T23:59:00-04:00",
  publishAt: "2026-09-01T09:00:00-04:00",
  artworkUrls: art.slice(1, 6),
};

const series = {
  id: "series-1",
  name: "BoroCrew After Hours",
  description: "A little place for the songs we keep coming back to.",
  timezone: "America/New_York",
  coverImageUrl: art[1],
  fallbackArtworkUrl: art[0],
  accentColor: "#15803d",
  isAdmin: true,
};

const profile = {
  id: "me",
  displayName: "Mara Green",
  spotifyProfileImageUrl: null,
  isMe: true,
  historyCount: 18,
  nextCursor: null,
  stats: {
    submissionCount: 18,
    uniqueTrackCount: 17,
    uniqueArtistCount: 15,
    uniqueAlbumCount: 16,
    uniqueGenreCount: genres.length,
    diversityScore: 82,
    genreTaggedTrackCount: 17,
    genreSpread: genres,
    topArtists: [
      { name: "The Lanterns", count: 4 },
      { name: "Marina Fields", count: 3 },
      { name: "Pale Coast", count: 3 },
      { name: "Isaac June", count: 2 },
      { name: "Static Bloom", count: 2 },
      { name: "Milo Dawn", count: 2 },
      { name: "Sister Ray", count: 1 },
      { name: "Juniper Park", count: 1 },
      { name: "Low Tide", count: 1 },
      { name: "Lumen", count: 1 },
    ],
    affinity: contributors.slice(1).map((contributor, index) => ({
      id: contributor.id,
      displayName: contributor.displayName,
      spotifyProfileImageUrl: contributor.spotifyProfileImageUrl,
      affinity: 78 - index * 13,
      sharedRoundCount: 12 - index * 2,
      sharedGenres: contributor.genres.slice(0, 3).map((genre) => genre.name),
    })),
  },
  submissions: Array.from({ length: 12 }, (_, index) => ({
    id: `history-${index}`,
    note: index === 0 ? "The first song I played after moving." : null,
    roundId: index % 2 ? "round-august" : "round-open",
    roundTitle: index % 2 ? "August favorites" : "September after dark",
    seriesId: "series-1",
    seriesName: "BoroCrew After Hours",
    submittedAt: `2026-0${Math.max(1, 9 - index)}-15T18:00:00-04:00`,
    track: tracks[index % tracks.length],
  })),
};

const adminSeries = {
  ...series,
  slug: "after-hours",
  isArchived: false,
  autoStartNextRound: true,
  defaultPolicies: [],
  roundPlan: {
    kind: "calendar",
    full_month: true,
    open_day: 1,
    duration_days: 30,
    publish_delay_minutes: 0,
    title_template: "{month} favorites",
    submission_limit: 3,
  },
  rounds: [
    { ...openRound, publisherAccountId: "spotify-me" },
    { ...publishedRound, submissionLimit: 3, publisherAccountId: "spotify-me" },
  ],
  groups: [],
};

const connections = [
  {
    id: "spotify-me",
    provider: "spotify",
    displayName: "Mara on Spotify",
    profileImageUrl: null,
    isActive: true,
    disconnectedAt: null,
    visibility: "round_members",
  },
  {
    id: "lastfm-me",
    provider: "lastfm",
    displayName: "maragreen",
    profileImageUrl: null,
    isActive: true,
    disconnectedAt: null,
    visibility: "round_members",
  },
];

function responseFor(path: string) {
  if (path === "/api/v1/auth/session") {
    return {
      csrfCookieName: "borocrew_csrf",
      expiresAt: "2026-10-01T00:00:00-04:00",
      user: {
        id: "me",
        email: "mara@example.test",
        displayName: "Mara Green",
        platformRole: "admin",
      },
    };
  }
  if (path === "/api/v1/series") return [{ ...series, featuredRound: openRound }];
  if (path === "/api/v1/series/series-1") {
    return {
      ...series,
      rounds: [openRound, publishedRound],
      stats: {
        roundCount: 18,
        songCount: 54,
        uniqueTrackCount: 51,
        artistCount: 42,
        genreTaggedTrackCount: 49,
        contributors,
        genreSpread: genres,
      },
    };
  }
  if (path === "/api/v1/rounds/round-open") return openRound;
  if (path === "/api/v1/rounds/round-open/submissions") return submissions;
  if (path === "/api/v1/rounds/round-open/draft") return { track: null, note: null };
  if (path === "/api/v1/rounds/round-open/listening-suggestions") return tracks.slice(0, 3);
  if (path === "/api/v1/profiles/me") return profile;
  if (path === "/api/v1/connections") return connections;
  if (path === "/api/v1/admin/series/series-1") return adminSeries;
  if (path === "/api/v1/admin/series/series-1/members") {
    return contributors.map(({ id, displayName }) => ({
      id,
      displayName,
      email: `${id}@example.test`,
    }));
  }
  return [];
}

export async function installApiFixtures(page: Page) {
  await page.route("**/api/v1/**", async (route: Route) => {
    const request = route.request();
    const url = new URL(request.url());
    const response = responseFor(url.pathname);
    await route.fulfill({ status: request.method() === "POST" ? 201 : 200, json: response });
  });
}

export async function applyVisualPreferences(page: Page, dark: boolean) {
  await page.addInitScript(
    (theme) => {
      Date.now = () => new Date("2026-09-09T12:00:00-04:00").getTime();
      window.localStorage.setItem("music-rounds-theme", theme);
      document.documentElement.dataset.theme = theme;
      const style = document.createElement("style");
      style.textContent = `
      *, *::before, *::after {
        animation: none !important;
        transition: none !important;
        caret-color: transparent !important;
      }
    `;
      document.head.append(style);
    },
    dark ? "dark" : "light",
  );
}
