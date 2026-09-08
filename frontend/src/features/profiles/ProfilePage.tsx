import { useQuery } from "@tanstack/react-query";
import type { CSSProperties } from "react";
import { Album, Disc3, Music2, UsersRound } from "lucide-react";
import { Link, useParams } from "react-router";

import { api } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import type { components } from "../../api/schema";
import { StatePanel } from "../../components/ui/StatePanel";
import { avatarStyle } from "../../lib/avatar";
import { formatDate } from "../../lib/format";
import { ConnectionsPanel } from "../connections/ConnectionsPage";
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
  const profile = useQuery({
    queryKey,
    queryFn: () => api<Profile>(endpoint),
    retry: false,
  });
  if (profile.isLoading)
    return (
      <main className="shell narrow-page-shell">
        <StatePanel kind="loading" title="Finding this listening history">
          Gathering the tracks, artists, and rounds behind it.
        </StatePanel>
      </main>
    );
  if (profile.isError || !profile.data)
    return (
      <main className="shell narrow-page-shell">
        <StatePanel kind="error" title="Profile unavailable">
          This listener may not have shared history with you yet.{" "}
          <Link to="/">Return to your series</Link>
        </StatePanel>
      </main>
    );
  const item = profile.data;
  const possessiveName = item.isMe ? "Your" : `${item.displayName}’s`;
  return (
    <main className="shell profile-shell">
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
        <div className="profile-variety" aria-label="Artist variety score">
          <div
            className="variety-orbit"
            style={{ "--variety": `${item.stats.diversityScore}%` } as CSSProperties}
          >
            <strong>{item.stats.diversityScore}</strong>
            <span>variety</span>
          </div>
          <p>How often a shared pick introduces a different artist.</p>
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
            <GenreSpread genres={item.stats.genreSpread} />
          </section>
          <section className="panel profile-history" aria-labelledby="profile-history-title">
            <div className="section-heading">
              <div>
                <p className="eyebrow">The record</p>
                <h2 id="profile-history-title">Shared tracks</h2>
              </div>
              <span className="profile-history-count">
                {item.historyCount} pick{item.historyCount === 1 ? "" : "s"}
              </span>
            </div>
            <div className="profile-submission-list">
              {item.submissions.map((submission) => (
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
          </section>
        </>
      ) : (
        <StatePanel title="No shared tracks yet">
          Once a track lands in a round, its artist, album, and genre trail will take shape here.
        </StatePanel>
      )}
      {includeConnections && (
        <section className="profile-connections" aria-labelledby="connections-title">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Your setup</p>
              <h2 id="connections-title">Connected services</h2>
            </div>
          </div>
          <ConnectionsPanel />
        </section>
      )}
    </main>
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

function ActivityChart({ activity }: { activity: Profile["stats"]["activity"] }) {
  const maximum = Math.max(...activity.map((item) => item.count), 1);
  return (
    <section className="panel profile-chart activity-chart">
      <div className="profile-chart-heading">
        <div>
          <p className="eyebrow">Pacing</p>
          <h2>When the picks landed</h2>
        </div>
        <span>Recent months with music</span>
      </div>
      <div className="activity-bars" aria-label="Submissions by month">
        {activity.map((item) => (
          <div
            className="activity-bar"
            key={item.month}
            title={`${item.label}: ${item.count} picks`}
          >
            <span className="activity-count">{item.count || ""}</span>
            <i
              style={
                {
                  "--height": `${Math.max((item.count / maximum) * 100, item.count ? 10 : 3)}%`,
                } as CSSProperties
              }
            />
            <small>{`${item.label.slice(0, 3)} ’${item.month.slice(2, 4)}`}</small>
          </div>
        ))}
      </div>
    </section>
  );
}

function TopArtists({ artists }: { artists: Profile["stats"]["topArtists"] }) {
  const maximum = Math.max(...artists.map((item) => item.count), 1);
  return (
    <section className="panel profile-chart profile-top-artists">
      <div className="profile-chart-heading">
        <div>
          <p className="eyebrow">Repeat listens</p>
          <h2>Most shared artists</h2>
        </div>
      </div>
      <ol>
        {artists.map((artist) => (
          <li key={artist.name}>
            <span>{artist.name}</span>
            <div aria-label={`${artist.count} picks`}>
              <i style={{ "--width": `${(artist.count / maximum) * 100}%` } as CSSProperties} />
            </div>
            <strong>{artist.count}</strong>
          </li>
        ))}
      </ol>
    </section>
  );
}

function GenreSpread({ genres }: { genres: Profile["stats"]["genreSpread"] }) {
  return (
    <section className="panel profile-chart profile-genres">
      <div className="profile-chart-heading">
        <div>
          <p className="eyebrow">Genre fingerprint</p>
          <h2>Where it leans</h2>
        </div>
      </div>
      {genres.length ? (
        <div className="genre-cloud">
          {genres.map((genre, index) => (
            <span className={`genre-token genre-token-${index % 4}`} key={genre.name}>
              {genre.name} <small>{genre.count}</small>
            </span>
          ))}
        </div>
      ) : (
        <p className="profile-chart-empty">
          Genre tags will appear as Spotify-tagged picks make their way into the record.
        </p>
      )}
    </section>
  );
}
