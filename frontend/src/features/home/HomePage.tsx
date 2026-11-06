import { lazy, Suspense, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { Disc3, Plus, ArrowUpRight } from "lucide-react";
import { Link } from "react-router";
import { api } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import type { components } from "../../api/schema";
import { ArtworkMosaic } from "../../components/ArtworkMosaic";
import { Button, buttonVariants } from "../../components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogTitle,
  DialogDescription,
  DialogTrigger,
} from "../../components/ui/dialog";
import { PageSkeleton } from "../../components/ui/PageSkeleton";
import { StatePanel } from "../../components/ui/StatePanel";
import { GuessWhoPhase } from "../rounds/GuessWhoPhase";
import { formatDate, formatDateOnly, formatDeadline } from "../../lib/format";
import { roundAction, sortHomeSeries, type HomeSeries } from "./homeState";
import "./home.css";

const SeriesCreatePanel = lazy(() =>
  import("../admin/SeriesCreatePanel").then((module) => ({ default: module.SeriesCreatePanel })),
);

export function HomePage({ signedOut }: { signedOut: ReactNode }) {
  const session = useQuery({
    queryKey: queryKeys.session(),
    queryFn: () => api<components["schemas"]["SessionResponse"]>("/auth/session"),
    retry: false,
  });
  const series = useQuery({
    queryKey: queryKeys.series(),
    queryFn: () => api<HomeSeries[]>("/series"),
    enabled: session.isSuccess,
    refetchInterval: 60_000,
  });
  if (session.isLoading)
    return <PageSkeleton label="Getting your music space ready" variant="dashboard" />;
  if (!session.data) return signedOut;
  if (series.isPending) return <PageSkeleton label="Finding your series" variant="dashboard" />;
  // The query refreshes each minute; use its timestamp consistently for time-sensitive copy.
  const now = series.dataUpdatedAt || session.dataUpdatedAt;
  const items = sortHomeSeries(series.data ?? [], now);
  const current = items.find(
    (item) => item.featuredRound && item.featuredRound.status !== "published",
  );
  const latest = items
    .filter((item) => item.latestPublishedRound)
    .sort(
      (a, b) =>
        Date.parse(b.latestPublishedRound!.publishedAt ?? b.latestPublishedRound!.publishAt) -
        Date.parse(a.latestPublishedRound!.publishedAt ?? a.latestPublishedRound!.publishAt),
    )[0];
  const others = items.filter((item) => {
    if (item.id === current?.id) return false;
    if (item.id === latest?.id)
      return Boolean(item.featuredRound && item.featuredRound.status !== "published");
    return true;
  });
  return (
    <main className="shell page-shell home-shell">
      <header className="home-heading">
        <div>
          <p className="eyebrow">Your listening room</p>
          <h1>
            Welcome back{session.data.user.displayName ? `, ${session.data.user.displayName}` : ""}.
          </h1>
          <p>A few picks. A shared playlist. Something new to hear.</p>
        </div>
        {session.data.user.platformRole === "admin" && (
          <Dialog>
            <DialogTrigger render={<Button variant="outline" />}>
              <Plus size={16} aria-hidden="true" />
              Create a series
            </DialogTrigger>
            <DialogContent className="home-create-dialog">
              <DialogTitle className="sr-only">Start a new series</DialogTitle>
              <DialogDescription className="sr-only">
                Create a space to share music with your group.
              </DialogDescription>
              <Suspense fallback={<p role="status">Loading series creation tools…</p>}>
                <SeriesCreatePanel />
              </Suspense>
            </DialogContent>
          </Dialog>
        )}
      </header>
      {series.isError && (
        <StatePanel kind="error" title="We couldn’t load your series">
          <Button variant="outline" onClick={() => series.refetch()}>
            Try again
          </Button>
        </StatePanel>
      )}
      {series.isSuccess && items.length === 0 && (
        <StatePanel title="No series yet">
          {session.data.user.platformRole === "admin"
            ? "Create a series to start sharing music with your group."
            : "Once you are added to a series, its rounds and playlists will appear here."}
        </StatePanel>
      )}
      {(current || latest) && (
        <div className="home-feature-grid">
          {current && <CurrentRound series={current} now={now} />}
          {latest && <LatestPlaylist series={latest} />}
        </div>
      )}
      {others.length > 0 && (
        <section className="home-other-series" aria-labelledby="home-series-heading">
          <h2 id="home-series-heading">
            {current || latest ? "More from your series" : "Your series"}
          </h2>
          <div className="home-series-grid">
            {others.map((item) => (
              <SmallSeries key={item.id} series={item} now={now} />
            ))}
          </div>
        </section>
      )}
    </main>
  );
}

function SeriesLink({ series }: { series: HomeSeries }) {
  return (
    <Link
      className="home-series-link"
      aria-label={`Open ${series.name}`}
      to={`/series/${series.id}`}
    >
      {series.name}
      <ArrowUpRight size={15} aria-hidden="true" />
    </Link>
  );
}

function CurrentRound({ series, now }: { series: HomeSeries; now: number }) {
  const round = series.featuredRound!;
  const action = roundAction(round, now);
  return (
    <article className="home-card home-current">
      <div className="home-card-top">
        <p className="eyebrow">
          {action.phase === "Open now" ? "Your current round" : action.phase}
        </p>
        <span className="home-phase">{action.phase}</span>
      </div>
      <SeriesLink series={series} />
      <h2>
        <Link to={`/rounds/${round.id}`}>{round.title}</Link>
      </h2>
      {round.prompt && <p className="home-prompt">{round.prompt}</p>}
      <div className="home-progress">
        <p>{action.message}</p>
        {round.isMember && round.submissionLimit > 0 && (
          <>
            <progress
              aria-label="Your submitted tracks"
              max={Math.max(round.submissionLimit, round.yourSubmissionCount)}
              value={round.yourSubmissionCount}
            />
            <small>
              {round.yourSubmissionCount} of {round.submissionLimit} picks shared
            </small>
          </>
        )}
      </div>
      <div className="home-card-footer">
        <p className="home-timing">
          {action.phase === "Open now" ? (
            <>
              <strong>{formatDeadline(round.closesAt)}</strong>
              <span>{formatDate(round.closesAt)}</span>
            </>
          ) : action.phase === "Up next" ? (
            <span>Opens {formatDate(round.opensAt)}</span>
          ) : action.phase === "Coming soon" ? (
            <span>
              {Date.parse(round.publishAt) > now
                ? `Playlist arrives ${formatDate(round.publishAt)}`
                : "Waiting for release"}
            </span>
          ) : null}
        </p>
        <div className="home-actions">
          <Link
            data-slot="button"
            className={buttonVariants({ variant: action.priority < 2 ? "default" : "outline" })}
            to={action.to}
          >
            {action.label}
          </Link>
          {action.priority < 2 && (
            <Link
              data-slot="button"
              className={buttonVariants({ variant: "ghost", className: "home-secondary-action" })}
              to={`/rounds/${round.id}`}
            >
              Round details
            </Link>
          )}
        </div>
      </div>
    </article>
  );
}

function LatestPlaylist({ series }: { series: HomeSeries }) {
  const round = series.latestPublishedRound!;
  return (
    <article className="home-card home-latest">
      <div className="home-card-top">
        <p className="eyebrow">Ready to listen</p>
        <Disc3 aria-hidden="true" size={20} />
      </div>
      <SeriesLink series={series} />
      <div className="home-release">
        <div>
          <h2>
            <Link to={`/rounds/${round.id}`}>{round.title}</Link>
          </h2>
          <p>Released {formatDateOnly(round.publishedAt ?? round.publishAt)}</p>
        </div>
        {round.artworkUrls.length > 0 ? (
          <ArtworkMosaic
            artworkUrls={round.artworkUrls}
            label={`Album artwork from ${round.title}`}
          />
        ) : (
          <div className="home-record" aria-hidden="true">
            <Disc3 />
          </div>
        )}
      </div>
      <div className="home-card-footer">
        <GuessWhoPhase roundId={round.id} linked />
        <div className="home-actions">
          {round.spotifyPlaylistUrl && (
            <a
              data-slot="button"
              className={buttonVariants({ variant: "outline" })}
              href={round.spotifyPlaylistUrl}
              target="_blank"
              rel="noreferrer"
            >
              Open Spotify playlist
              <ArrowUpRight size={16} aria-hidden="true" />
            </a>
          )}
          <Link
            data-slot="button"
            className={buttonVariants({ variant: "ghost", className: "home-secondary-action" })}
            to={`/rounds/${round.id}`}
          >
            Release recap
          </Link>
        </div>
      </div>
    </article>
  );
}

function SmallSeries({ series, now }: { series: HomeSeries; now: number }) {
  const round = series.featuredRound;
  const action = round ? roundAction(round, now) : null;
  return (
    <article className="home-series-card">
      <SeriesLink series={series} />
      {round && action ? (
        <>
          <h3>
            <Link to={`/rounds/${round.id}`}>{round.title}</Link>
          </h3>
          <p>{action.message}</p>
          <Link className="home-small-action" to={action.to}>
            {action.label}
            <ArrowUpRight size={15} aria-hidden="true" />
          </Link>
        </>
      ) : (
        <p>{series.description ?? "The first round will appear here."}</p>
      )}
    </article>
  );
}
