import { useState, type CSSProperties } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarDays, Clock3, Disc3, ListMusic, UsersRound } from "lucide-react";
import { Link, useParams } from "react-router";

import { api, patch, post } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import type { components } from "../../api/schema";
import { ConfirmDialog } from "../../components/ui/ConfirmDialog";
import { StatePanel } from "../../components/ui/StatePanel";
import { useToast } from "../../components/ui/ToastProvider";
import { avatarStyle } from "../../lib/avatar";
import { formatDate } from "../../lib/format";

type Round = components["schemas"]["RoundDetailResponse"];
type Submission = components["schemas"]["SubmissionResponse"];
type SeriesHistory = components["schemas"]["SeriesHistoryResponse"];

export function RoundPage() {
  const { roundId } = useParams();
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const [submissionToWithdraw, setSubmissionToWithdraw] = useState<Submission | null>(null);
  const round = useQuery({
    queryKey: queryKeys.round(roundId),
    queryFn: () => api<Round>(`/rounds/${roundId}`),
    enabled: Boolean(roundId),
    retry: false,
  });
  const submissions = useQuery({
    queryKey: queryKeys.roundSubmissions(roundId),
    queryFn: () => api<Submission[]>(`/rounds/${roundId}/submissions`),
    enabled: Boolean(roundId) && round.isSuccess,
    retry: false,
  });
  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: queryKeys.roundSubmissions(roundId) });
    queryClient.invalidateQueries({ queryKey: queryKeys.round(roundId) });
  };
  const withdraw = useMutation({
    mutationFn: (submissionId: string) =>
      post<void>(`/rounds/submissions/${submissionId}/withdraw`, undefined),
    onSuccess: () => {
      invalidate();
      setSubmissionToWithdraw(null);
      showToast({
        title: "Submission withdrawn",
        description: "You can choose another track while this round is still open.",
      });
    },
    onError: () =>
      showToast({
        title: "Couldn’t withdraw submission",
        description: "Try again in a moment.",
        tone: "error",
      }),
  });
  const updateNote = useMutation({
    mutationFn: ({ submissionId, note }: { submissionId: string; note: string | null }) =>
      patch<void>(`/rounds/submissions/${submissionId}`, { note }),
    onSuccess: () => {
      invalidate();
      showToast({ title: "Note saved", description: "Your submission note is updated." });
    },
    onError: () =>
      showToast({
        title: "Couldn’t save note",
        description: "Try again in a moment.",
        tone: "error",
      }),
  });

  if (round.isLoading)
    return (
      <main className="shell narrow-page-shell">
        <StatePanel kind="loading" title="Loading this round">
          Gathering its schedule and submissions.
        </StatePanel>
      </main>
    );
  if (round.isError || !round.data) return <UnavailableRound />;

  const item = round.data;
  const mySubmissionCount = submissions.data?.filter(
    (entry) => entry.isMine && entry.status === "accepted",
  ).length;
  return (
    <main className="shell round-page-shell">
      <Link className="back" to={item.seriesId ? `/series/${item.seriesId}` : "/"}>
        ← Back to series
      </Link>
      <RoundOverview round={item} mySubmissionCount={mySubmissionCount} />
      {item.status === "published" && submissions.data && (
        <ReleaseRecap round={item} submissions={submissions.data} />
      )}
      <RoundSubmissions
        roundId={item.id}
        submissions={submissions}
        roundIsOpen={item.status === "open"}
        onWithdraw={setSubmissionToWithdraw}
        onSaveNote={(id, note) => updateNote.mutate({ submissionId: id, note })}
      />
      <ConfirmDialog
        open={Boolean(submissionToWithdraw)}
        title="Withdraw this submission?"
        description={
          <>
            “{submissionToWithdraw?.track.name}” will no longer be included in the finished
            playlist. You can submit another track while the round is open.
          </>
        }
        confirmLabel="Withdraw submission"
        isPending={withdraw.isPending}
        onOpenChange={(open) => {
          if (!open && !withdraw.isPending) setSubmissionToWithdraw(null);
        }}
        onConfirm={() => {
          if (submissionToWithdraw) withdraw.mutate(submissionToWithdraw.id);
        }}
      />
    </main>
  );
}

function UnavailableRound() {
  return (
    <main className="shell">
      <StatePanel kind="error" title="Round unavailable">
        You may no longer be a contributor in this round. <Link to="/">Return to your rounds</Link>
      </StatePanel>
    </main>
  );
}

function RoundOverview({
  round,
  mySubmissionCount,
}: {
  round: Round;
  mySubmissionCount: number | undefined;
}) {
  const hasCapacity = mySubmissionCount === undefined || mySubmissionCount < round.submissionLimit;
  return (
    <section
      className="panel detail round-overview"
      style={
        {
          "--round-cover": round.backgroundArtworkUrl
            ? `url(${round.backgroundArtworkUrl})`
            : "none",
        } as CSSProperties
      }
    >
      <span className={`status ${round.status}`}>{round.status}</span>
      <h1>{round.title}</h1>
      <p>
        Share up to {round.submissionLimit} track{round.submissionLimit === 1 ? "" : "s"} with this
        group before the release date.
      </p>
      {round.prompt && <p className="round-prompt">Prompt: {round.prompt}</p>}
      <div className="round-summary" aria-label="Round summary">
        <div>
          <ListMusic aria-hidden="true" size={18} />
          <span>
            <strong>
              {mySubmissionCount === undefined
                ? "…"
                : `${mySubmissionCount} of ${round.submissionLimit}`}
            </strong>
            <small>Your submissions</small>
          </span>
        </div>
        <div>
          <UsersRound aria-hidden="true" size={18} />
          <span>
            <strong>{round.status === "open" ? "Open now" : round.status}</strong>
            <small>Round status</small>
          </span>
        </div>
      </div>
      <div className="timeline">
        <div>
          <strong>
            <CalendarDays aria-hidden="true" size={14} /> Opens
          </strong>
          <span>{formatDate(round.opensAt)}</span>
        </div>
        <div>
          <strong>
            <Clock3 aria-hidden="true" size={14} /> Closes
          </strong>
          <span>{formatDate(round.closesAt)}</span>
        </div>
        <div>
          <strong>
            <CalendarDays aria-hidden="true" size={14} /> Releases
          </strong>
          <span>{formatDate(round.publishAt)}</span>
        </div>
      </div>
      {round.spotifyPlaylistUrl && (
        <a
          className="history-link"
          href={round.spotifyPlaylistUrl}
          target="_blank"
          rel="noreferrer"
        >
          Open Spotify playlist
        </a>
      )}
      {round.status === "open" && hasCapacity ? (
        <Link className="button" to={`/rounds/${round.id}/submit`}>
          Choose a track
        </Link>
      ) : round.status === "open" ? (
        <p className="round-capacity-note">
          You&apos;re all set! You can still change your mind before the end of the round by
          modifying your submissions below.
        </p>
      ) : (
        <p className="muted">Submissions are currently closed.</p>
      )}
      {round.seriesId && (
        <Link className="history-link" to={`/series/${round.seriesId}`}>
          View series history
        </Link>
      )}
      {round.canManage && (
        <Link className="history-link" to={`/admin/rounds/${round.id}`}>
          Manage this round
        </Link>
      )}
    </section>
  );
}

function ReleaseRecap({ round, submissions }: { round: Round; submissions: Submission[] }) {
  const artwork = round.artworkUrls;
  return (
    <section className="panel release-recap">
      <div>
        <p className="eyebrow">Release recap</p>
        <h2>{round.title}</h2>
        <p>
          {round.submittedCount} contributor{round.submittedCount === 1 ? "" : "s"} shared{" "}
          {submissions.length} track{submissions.length === 1 ? "" : "s"}.
        </p>
      </div>
      {artwork.length > 0 && (
        <ArtworkMosaic artworkUrls={artwork} label="Album art from this release" />
      )}
      <NowSpinning
        tracks={submissions
          .slice(0, 4)
          .map((submission) => `${submission.track.name} — ${submission.track.artist}`)}
      />
    </section>
  );
}

function ArtworkMosaic({ artworkUrls, label }: { artworkUrls: string[]; label: string }) {
  return (
    <div className="artwork-mosaic" aria-label={label}>
      {artworkUrls.map((url, index) => (
        <img key={`${url}-${index}`} src={url} alt="" />
      ))}
    </div>
  );
}

function NowSpinning({ tracks }: { tracks: string[] }) {
  return (
    <p className="now-spinning" aria-label="Now spinning">
      <span>Now spinning</span>
      <span className="now-spinning-viewport">
        <strong>{tracks.join(" · ")}</strong>
      </span>
    </p>
  );
}

function RoundSubmissions({
  roundId,
  submissions,
  roundIsOpen,
  onWithdraw,
  onSaveNote,
}: {
  roundId: string;
  submissions: ReturnType<typeof useQuery<Submission[]>>;
  roundIsOpen: boolean;
  onWithdraw: (submission: Submission) => void;
  onSaveNote: (id: string, note: string | null) => void;
}) {
  if (submissions.isLoading)
    return (
      <StatePanel kind="loading" title="Loading submissions">
        Checking what the group has shared so far.
      </StatePanel>
    );
  if (submissions.isError)
    return (
      <StatePanel kind="error" title="We couldn’t load submissions">
        Refresh the page to try again.
      </StatePanel>
    );
  const entries = submissions.data ?? [];
  return (
    <section className="panel submission-history" aria-labelledby="submissions-heading">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Shared so far</p>
          <h2 id="submissions-heading">Submissions</h2>
        </div>
        <span className="submission-count">
          {entries.filter((entry) => entry.status === "accepted").length} track
          {entries.filter((entry) => entry.status === "accepted").length === 1 ? "" : "s"}
        </span>
      </div>
      {entries.length === 0 ? (
        <StatePanel title="The playlist is waiting for its first track">
          Be the one to set the tone for this round.
        </StatePanel>
      ) : (
        <ul>
          {entries.map((entry) => (
            <li key={entry.id} className={entry.status === "withdrawn" ? "withdrawn" : ""}>
              {entry.track.artworkUrl ? (
                <img className="submission-artwork" src={entry.track.artworkUrl} alt="" />
              ) : (
                <span
                  className="submission-artwork submission-artwork-placeholder"
                  aria-label="Album art unavailable"
                >
                  <Disc3 aria-hidden="true" size={22} />
                </span>
              )}
              <div>
                <strong>{entry.track.name}</strong>
                <span>
                  {entry.track.artist}
                  {entry.track.album ? ` · ${entry.track.album}` : ""}
                </span>
              </div>
              <span className="submission-contributor">
                <small>
                  Submitted by {entry.contributor.displayName ?? "Unknown listener"}
                  {entry.isMine ? " (you)" : ""}
                </small>
                {entry.contributor.spotifyProfileImageUrl ? (
                  <img
                    className="contributor-avatar"
                    src={entry.contributor.spotifyProfileImageUrl}
                    alt={`${entry.contributor.displayName ?? "Contributor"}'s Spotify profile`}
                  />
                ) : (
                  <span
                    className="contributor-avatar contributor-avatar-fallback"
                    style={avatarStyle(entry.contributor.displayName)}
                    aria-label={`${entry.contributor.displayName ?? "Unknown listener"}'s profile`}
                  >
                    {(entry.contributor.displayName ?? "?").slice(0, 1).toUpperCase()}
                  </span>
                )}
              </span>
              {entry.note && <p>{entry.note}</p>}
              {entry.isMine && entry.status === "accepted" && roundIsOpen && (
                <details>
                  <summary>Manage your submission</summary>
                  <form
                    onSubmit={(event) => {
                      event.preventDefault();
                      const form = new FormData(event.currentTarget);
                      onSaveNote(entry.id, String(form.get("note") || "").trim() || null);
                    }}
                  >
                    <label htmlFor={`note-${entry.id}`}>Note</label>
                    <textarea
                      id={`note-${entry.id}`}
                      name="note"
                      defaultValue={entry.note ?? ""}
                      maxLength={4000}
                    />
                    <div className="inline-actions">
                      <button type="submit">Save note</button>
                      <Link to={`/rounds/${roundId}/submit?replace=${entry.id}`}>
                        Replace track
                      </Link>
                      <button type="button" className="danger" onClick={() => onWithdraw(entry)}>
                        Withdraw
                      </button>
                    </div>
                  </form>
                </details>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export function SeriesPage() {
  const { seriesId } = useParams();
  const series = useQuery({
    queryKey: queryKeys.seriesDetail(seriesId),
    queryFn: () => api<SeriesHistory>(`/series/${seriesId}`),
    enabled: Boolean(seriesId),
    retry: false,
  });
  if (series.isLoading)
    return (
      <main className="shell narrow-page-shell">
        <StatePanel kind="loading" title="Loading series history">
          Collecting the rounds you can revisit.
        </StatePanel>
      </main>
    );
  if (series.isError || !series.data)
    return (
      <main className="shell narrow-page-shell">
        <StatePanel kind="error" title="Series unavailable">
          You do not have access to this series. <Link to="/">Return to your series</Link>
        </StatePanel>
      </main>
    );
  const item = series.data;
  // The API already sorts an open round ahead of the archive, so the first
  // round is the one worth leading with. The archive below is releases only,
  // which keeps an unfinished round from being listed with a release date it
  // has not reached yet.
  const featuredRound = item.rounds[0];
  const publishedRounds = item.rounds.filter(
    (round) => round.status === "published" && round.id !== featuredRound?.id,
  );
  const upcomingRounds = item.rounds.filter(
    (round) => round.status !== "published" && round.id !== featuredRound?.id,
  );
  return (
    <main className="shell">
      <Link className="back" to="/">
        ← Your series
      </Link>
      <section
        className="panel detail series-overview"
        style={
          {
            "--series-cover":
              (item.coverImageUrl ?? item.fallbackArtworkUrl)
                ? `url(${item.coverImageUrl ?? item.fallbackArtworkUrl})`
                : "none",
          } as CSSProperties
        }
      >
        <div className="series-page-heading">
          <div>
            <p className="eyebrow">Series · {item.timezone}</p>
            <h1>{item.name}</h1>
            {item.description && <p>{item.description}</p>}
          </div>
          {item.isAdmin && (
            <Link className="button button-secondary" to={`/admin/series/${item.id}`}>
              Manage series
            </Link>
          )}
        </div>
        <p className="muted">A record of the rounds and releases your group has made together.</p>
        <section className="series-stats" aria-label="Series statistics">
          <div>
            <strong>{item.stats.roundCount}</strong>
            <span>rounds</span>
          </div>
          <div>
            <strong>{item.stats.songCount}</strong>
            <span>songs</span>
          </div>
          <div>
            <strong>{item.stats.artistCount}</strong>
            <span>artists</span>
          </div>
          <SeriesContributors contributors={item.stats.contributors} />
        </section>
      </section>
      {item.rounds.length === 0 && (
        <StatePanel title="No rounds yet">
          When this series starts a round, it will appear here.
        </StatePanel>
      )}
      {featuredRound && <FeaturedRound round={featuredRound} />}
      {(publishedRounds.length > 0 || upcomingRounds.length > 0) && (
        <section className="panel series-release-list">
          <div className="section-heading">
            <div>
              <p className="eyebrow">The archive</p>
              <h2>Rounds</h2>
            </div>
          </div>
          {upcomingRounds.length > 0 && (
            <div className="series-timeline" aria-label="Upcoming round timeline">
              {upcomingRounds.slice(0, 4).map((round) => (
                <Link key={round.id} to={`/rounds/${round.id}`}>
                  <span className={`status ${round.status}`}>{round.status}</span>
                  <strong>{round.title}</strong>
                  <small>
                    {round.status === "open"
                      ? `Closes ${formatDate(round.closesAt)}`
                      : `Opens ${formatDate(round.opensAt)}`}
                  </small>
                </Link>
              ))}
            </div>
          )}
          <div className="series-round-list">
            {publishedRounds.map((round) => (
              <Link className="series-round-item" key={round.id} to={`/rounds/${round.id}`}>
                {round.artworkUrls.length > 0 && (
                  <ArtworkMosaic
                    artworkUrls={round.artworkUrls}
                    label={`Album art from ${round.title}`}
                  />
                )}
                <span className={`status ${round.status}`}>{round.status}</span>
                <div>
                  <h2>{round.title}</h2>
                  <p>
                    Opened {formatDate(round.opensAt)} · Published {formatDate(round.publishAt)}
                  </p>
                </div>
              </Link>
            ))}
          </div>
        </section>
      )}
    </main>
  );
}

function SeriesContributors({
  contributors,
}: {
  contributors: SeriesHistory["stats"]["contributors"];
}) {
  return (
    <div className="series-contributors">
      <strong>Contributors</strong>
      <div className="contributor-stack">
        {contributors.length ? (
          contributors.map((contributor) =>
            contributor.spotifyProfileImageUrl ? (
              <img
                key={contributor.id}
                src={contributor.spotifyProfileImageUrl}
                title={contributor.displayName}
                alt={contributor.displayName}
              />
            ) : (
              <span
                key={contributor.id}
                title={contributor.displayName}
                style={avatarStyle(contributor.displayName)}
                aria-label={contributor.displayName}
              >
                {contributor.displayName.slice(0, 1).toUpperCase()}
              </span>
            ),
          )
        ) : (
          <small>No submissions yet</small>
        )}
      </div>
    </div>
  );
}

function FeaturedRound({ round }: { round: SeriesHistory["rounds"][number] }) {
  const active = round.status !== "published";
  return (
    <Link className="series-featured-round" to={`/rounds/${round.id}`}>
      <div>
        <p className="eyebrow">{active ? "Current round" : "Latest release"}</p>
        <h2>{round.title}</h2>
        <p>
          {active
            ? `Closes ${formatDate(round.closesAt)}`
            : `Released ${formatDate(round.publishAt)}`}
        </p>
        {round.prompt && <p className="featured-prompt">Prompt: {round.prompt}</p>}
      </div>
      {round.artworkUrls.length > 0 && (
        <ArtworkMosaic artworkUrls={round.artworkUrls} label={`Album art from ${round.title}`} />
      )}
      <div>
        <span className={`status ${round.status}`}>{round.status}</span>
      </div>
    </Link>
  );
}
