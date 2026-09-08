import { useInfiniteQuery } from "@tanstack/react-query";
import type { CSSProperties } from "react";
import { Album, Disc3, Music2, UsersRound } from "lucide-react";
import { Link, useParams } from "react-router";

import { api } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import type { components } from "../../api/schema";
import { StatePanel } from "../../components/ui/StatePanel";
import { avatarStyle } from "../../lib/avatar";
import { formatDate } from "../../lib/format";
import { ConnectionsPanel } from "../connections/ConnectionsPanel";
import "./profiles.css";

type Profile = components["schemas"]["ProfileResponse"];

export function ProfilePage() {
  return <ProfileView endpoint="/profiles/me" queryKey={queryKeys.profile()} includeConnections />;
}

export function ContributorProfilePage() {
  const { userId } = useParams();
  return <ProfileView endpoint={`/profiles/${userId}`} queryKey={queryKeys.profile(userId)} />;
}

function ProfileView({
  endpoint,
  queryKey,
  includeConnections = false,
}: {
  endpoint: string;
  queryKey: readonly unknown[];
  includeConnections?: boolean;
}) {
  const profile = useInfiniteQuery({
    queryKey,
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) =>
      api<Profile>(
        `${endpoint}?${new URLSearchParams({
          limit: "30",
          ...(pageParam ? { cursor: pageParam } : {}),
        })}`,
      ),
    getNextPageParam: (lastPage) => lastPage.nextCursor ?? undefined,
    retry: false,
  });
  const item = profile.data?.pages[0];
  const submissions = profile.data?.pages.flatMap((page) => page.submissions) ?? [];

  return (
    <main className="shell profile-shell">
      {profile.isLoading && (
        <StatePanel kind="loading" title="Finding this listening history">
          Gathering the tracks, artists, and rounds behind it.
        </StatePanel>
      )}
      {profile.isError || !item ? (
        <>
          {!profile.isLoading && (
            <StatePanel
              kind="error"
              title={includeConnections ? "Listening profile unavailable" : "Profile unavailable"}
            >
              {includeConnections ? (
                "Your connection settings are still available below."
              ) : (
                <>
                  This listener may not have shared history with you yet.{" "}
                  <Link to="/">Return to your series</Link>
                </>
              )}
            </StatePanel>
          )}
        </>
      ) : (
        <ProfileContent
          item={item}
          submissions={submissions}
          onLoadMore={() => profile.fetchNextPage()}
          hasMore={profile.hasNextPage}
          isLoadingMore={profile.isFetchingNextPage}
        />
      )}
      {includeConnections && <ProfileConnections />}
    </main>
  );
}

function ProfileContent({
  item,
  submissions,
  onLoadMore,
  hasMore,
  isLoadingMore,
}: {
  item: Profile;
  submissions: Profile["submissions"];
  onLoadMore: () => void;
  hasMore: boolean;
  isLoadingMore: boolean;
}) {
  const possessiveName = item.isMe ? "Your" : `${item.displayName}’s`;
  return (
    <>
      {!item.isMe && (
        <Link className="back" to="/">
          ← Your series
        </Link>
      )}
      <section className="panel profile-overview">
        <div className="profile-identity">
          {item.spotifyProfileImageUrl ? (
            <img className="profile-avatar" src={item.spotifyProfileImageUrl} alt="" />
          ) : (
            <span
              className="profile-avatar profile-avatar-fallback"
              style={avatarStyle(item.displayName)}
              aria-hidden="true"
            >
              {item.displayName.slice(0, 1).toUpperCase()}
            </span>
          )}
          <div>
            <p className="eyebrow">{item.isMe ? "Your listening profile" : "Listener profile"}</p>
            <h1>{item.isMe ? "Your record, so far." : item.displayName}</h1>
            <p>
              {item.stats.submissionCount
                ? `${possessiveName} picks across the rounds you share.`
                : "The first shared track will start the story."}
            </p>
          </div>
        </div>
        <div
          className="profile-variety"
          aria-label={`Artist variety score: ${item.stats.diversityScore}%`}
        >
          <div
            className="variety-orbit"
            style={{ "--variety": `${item.stats.diversityScore}%` } as CSSProperties}
          >
            <strong>{item.stats.diversityScore}</strong>
            <span>variety</span>
          </div>
          <p>How often a shared artist credit is someone new.</p>
        </div>
      </section>
      <section className="profile-stat-grid" aria-label="Listening profile statistics">
        <ProfileStat icon={Music2} label="Tracks shared" value={item.stats.submissionCount} />
        <ProfileStat
          icon={UsersRound}
          label="Artists explored"
          value={item.stats.uniqueArtistCount}
        />
        <ProfileStat icon={Album} label="Albums visited" value={item.stats.uniqueAlbumCount} />
        <ProfileStat icon={Disc3} label="Genre signals" value={item.stats.uniqueGenreCount} />
      </section>
      {item.stats.submissionCount > 0 ? (
        <>
          <section className="profile-insights-grid" aria-label="Listening profile insights">
            <ActivityChart activity={item.stats.activity} />
            <TopArtists artists={item.stats.topArtists} />
            <GenreSpread
              genres={item.stats.genreSpread}
              taggedTrackCount={item.stats.genreTaggedTrackCount}
              trackCount={item.stats.uniqueTrackCount}
            />
          </section>
          <section className="panel profile-history" aria-labelledby="profile-history-title">
            <div className="section-heading">
              <div>
                <p className="eyebrow">The record</p>
                <h2 id="profile-history-title">Shared tracks</h2>
              </div>
              <span className="profile-history-count">
                {submissions.length === item.historyCount
                  ? `${item.historyCount} pick${item.historyCount === 1 ? "" : "s"}`
                  : `Showing ${submissions.length} of ${item.historyCount}`}
              </span>
            </div>
            <div className="profile-submission-list">
              {submissions.map((submission) => (
                <article key={submission.id} className="profile-submission">
                  {submission.track.artworkUrl ? (
                    <img src={submission.track.artworkUrl} alt="" />
                  ) : (
                    <span className="profile-track-placeholder" aria-hidden="true">
                      <Music2 size={22} />
                    </span>
                  )}
                  <div className="profile-submission-track">
                    <strong>{submission.track.name}</strong>
                    <span>
                      {submission.track.artist}
                      {submission.track.album ? ` · ${submission.track.album}` : ""}
                    </span>
                    {submission.note && <em>“{submission.note}”</em>}
                  </div>
                  <div className="profile-submission-round">
                    <Link to={`/series/${submission.seriesId}`}>{submission.seriesName}</Link>
                    <Link to={`/rounds/${submission.roundId}`}>{submission.roundTitle}</Link>
                    <small>{formatDate(submission.submittedAt)}</small>
                  </div>
                </article>
              ))}
            </div>
            {hasMore && (
              <button
                className="button secondary profile-load-more"
                type="button"
                onClick={onLoadMore}
                disabled={isLoadingMore}
              >
                {isLoadingMore ? "Loading picks…" : "Show more picks"}
              </button>
            )}
          </section>
        </>
      ) : (
        <StatePanel title="No shared tracks yet">
          Once a track lands in a round, its artist, album, and genre trail will take shape here.
        </StatePanel>
      )}
    </>
  );
}

function ProfileConnections() {
  return (
    <section className="profile-connections" aria-labelledby="connections-title">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Your setup</p>
          <h2 id="connections-title">Connected services</h2>
        </div>
      </div>
      <ConnectionsPanel />
    </section>
  );
}

function ProfileStat({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof Music2;
  label: string;
  value: number;
}) {
  return (
    <div className="profile-stat">
      <Icon aria-hidden="true" size={18} />
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
}

/* The count rides on top of its bar and takes height of its own, so bars are
   drawn into the part of the track left over. Scaling every bar by the same
   factor keeps them comparable; letting the tallest fill the track instead
   pushed it and its label through the baseline. */
const BAR_TRACK_PERCENT = 86;

function ActivityChart({ activity }: { activity: Profile["stats"]["activity"] }) {
  const maximum = Math.max(...activity.map((item) => item.count), 1);
  return (
    <section className="panel profile-chart activity-chart">
      <div className="profile-chart-heading">
        <div>
          <p className="eyebrow">Pacing</p>
          <h2>When the picks landed</h2>
        </div>
        <span>Latest year of activity</span>
      </div>
      <ol className="activity-bars" aria-label="Submissions by month">
        {activity.map((item) => (
          <li className="activity-bar" key={item.month}>
            <div
              className="activity-column"
              style={
                {
                  "--height": `${Math.max((item.count / maximum) * BAR_TRACK_PERCENT, item.count ? 8 : 2)}%`,
                } as CSSProperties
              }
            >
              <span className="activity-count" aria-hidden="true">
                {item.count || ""}
              </span>
              <i aria-hidden="true" />
            </div>
            <small aria-hidden="true">
              {item.month.endsWith("-01")
                ? `${item.label.slice(0, 3)} ’${item.month.slice(2, 4)}`
                : item.label.slice(0, 3)}
            </small>
            <span className="profile-sr-only">{`${item.label}: ${item.count} picks`}</span>
          </li>
        ))}
      </ol>
    </section>
  );
}

function TopArtists({ artists }: { artists: Profile["stats"]["topArtists"] }) {
  const maximum = Math.max(...artists.map((item) => item.count), 1);
  return (
    <section className="panel profile-chart profile-top-artists">
      <div className="profile-chart-heading">
        <div>
          <p className="eyebrow">Your favorites</p>
          <h2>Most shared artists</h2>
        </div>
      </div>
      <ol>
        {artists.map((artist) => (
          <li key={artist.name}>
            <span>{artist.name}</span>
            <div aria-hidden="true">
              <i style={{ "--width": `${(artist.count / maximum) * 100}%` } as CSSProperties} />
            </div>
            <strong>{artist.count}</strong>
            <span className="profile-sr-only">{`${artist.count} picks`}</span>
          </li>
        ))}
      </ol>
    </section>
  );
}

function GenreSpread({
  genres,
  taggedTrackCount,
  trackCount,
}: {
  genres: Profile["stats"]["genreSpread"];
  taggedTrackCount: number;
  trackCount: number;
}) {
  return (
    <section className="panel profile-chart profile-genres">
      <div className="profile-chart-heading">
        <div>
          <p className="eyebrow">Genre fingerprint</p>
          <h2>Where it leans</h2>
        </div>
        <span>{`${taggedTrackCount} of ${trackCount} tracks tagged`}</span>
      </div>
      {genres.length ? (
        <div className="genre-cloud">
          {genres.map((genre) => (
            <span
              className={`genre-token genre-token-${genre.group.replace(" ", "-")}`}
              key={genre.name}
            >
              <i aria-hidden="true" />
              {genre.name} <small>{genre.count}</small>
            </span>
          ))}
        </div>
      ) : (
        <p className="profile-chart-empty">No genre tags have been cached for these picks yet.</p>
      )}
    </section>
  );
}
