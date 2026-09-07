import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarDays, Clock3, ListMusic, UsersRound } from "lucide-react";
import { Link, useParams } from "react-router";

import { api, patch, post } from "../../api/client";
import { ConfirmDialog } from "../../components/ui/ConfirmDialog";
import { StatePanel } from "../../components/ui/StatePanel";
import { useToast } from "../../components/ui/ToastProvider";
import { formatDate } from "../../lib/format";

type Round = {
  id: string;
  seriesId?: string;
  title: string;
  status: string;
  opensAt: string;
  closesAt: string;
  publishAt: string;
  submissionLimit: number;
};

type Submission = {
  id: string;
  status: "accepted" | "withdrawn";
  note: string | null;
  isMine: boolean;
  contributor: { id: string; displayName: string | null; spotifyProfileImageUrl: string | null };
  track: { name: string; artist: string; album: string | null; artworkUrl?: string | null };
};

type SeriesHistory = {
  id: string;
  name: string;
  description: string | null;
  timezone: string;
  isAdmin: boolean;
  rounds: Array<
    Pick<Round, "id" | "title" | "status" | "opensAt" | "closesAt" | "publishAt">
  >;
};

export function RoundPage() {
  const { roundId } = useParams();
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const [submissionToWithdraw, setSubmissionToWithdraw] = useState<Submission | null>(null);
  const round = useQuery({
    queryKey: ["round", roundId],
    queryFn: () => api<Round>(`/rounds/${roundId}`),
    enabled: Boolean(roundId),
    retry: false,
  });
  const submissions = useQuery({
    queryKey: ["round-submissions", roundId],
    queryFn: () => api<Submission[]>(`/rounds/${roundId}/submissions`),
    enabled: Boolean(roundId) && round.isSuccess,
    retry: false,
  });
  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["round-submissions", roundId] });
    queryClient.invalidateQueries({ queryKey: ["round", roundId] });
  };
  const withdraw = useMutation({
    mutationFn: (submissionId: string) =>
      post<void>(`/rounds/submissions/${submissionId}/withdraw`, undefined),
    onSuccess: () => {
      invalidate();
      setSubmissionToWithdraw(null);
      showToast({ title: "Submission withdrawn", description: "You can choose another track while this round is still open." });
    },
    onError: () => showToast({ title: "Couldn’t withdraw submission", description: "Try again in a moment.", tone: "error" }),
  });
  const updateNote = useMutation({
    mutationFn: ({
      submissionId,
      note,
    }: {
      submissionId: string;
      note: string | null;
    }) => patch<void>(`/rounds/submissions/${submissionId}`, { note }),
    onSuccess: () => {
      invalidate();
      showToast({ title: "Note saved", description: "Your submission note is updated." });
    },
    onError: () => showToast({ title: "Couldn’t save note", description: "Try again in a moment.", tone: "error" }),
  });

  if (round.isLoading) return <main className="shell narrow-page-shell"><StatePanel kind="loading" title="Loading this round">Gathering its schedule and submissions.</StatePanel></main>;
  if (round.isError || !round.data) return <UnavailableRound />;

  const item = round.data;
  const mySubmissionCount = submissions.data?.filter((entry) => entry.isMine && entry.status === "accepted").length;
  return (
    <main className="shell round-page-shell">
      <Link className="back" to="/">
        ← Your series
      </Link>
      <RoundOverview round={item} mySubmissionCount={mySubmissionCount} />
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
        description={<>“{submissionToWithdraw?.track.name}” will no longer be included in the finished playlist. You can submit another track while the round is open.</>}
        confirmLabel="Withdraw submission"
        isPending={withdraw.isPending}
        onOpenChange={(open) => { if (!open && !withdraw.isPending) setSubmissionToWithdraw(null); }}
        onConfirm={() => { if (submissionToWithdraw) withdraw.mutate(submissionToWithdraw.id); }}
      />
    </main>
  );
}

function UnavailableRound() {
  return (
    <main className="shell">
      <StatePanel kind="error" title="Round unavailable">You may no longer be a contributor in this round. <Link to="/">Return to your rounds</Link></StatePanel>
    </main>
  );
}

function RoundOverview({ round, mySubmissionCount }: { round: Round; mySubmissionCount: number | undefined }) {
  const hasCapacity = mySubmissionCount === undefined || mySubmissionCount < round.submissionLimit;
  return (
    <section className="panel detail">
      <span className={`status ${round.status}`}>{round.status}</span>
      <h1>{round.title}</h1>
      <p>Share up to {round.submissionLimit} track{round.submissionLimit === 1 ? "" : "s"} with this group before the release date.</p>
      <div className="round-summary" aria-label="Round summary">
        <div><ListMusic aria-hidden="true" size={18} /><span><strong>{mySubmissionCount === undefined ? "…" : `${mySubmissionCount} of ${round.submissionLimit}`}</strong><small>Your submissions</small></span></div>
        <div><UsersRound aria-hidden="true" size={18} /><span><strong>{round.status === "open" ? "Open now" : round.status}</strong><small>Round status</small></span></div>
      </div>
      <div className="timeline">
        <div>
          <strong><CalendarDays aria-hidden="true" size={14} /> Opens</strong>
          <span>{formatDate(round.opensAt)}</span>
        </div>
        <div>
          <strong><Clock3 aria-hidden="true" size={14} /> Closes</strong>
          <span>{formatDate(round.closesAt)}</span>
        </div>
        <div>
          <strong><CalendarDays aria-hidden="true" size={14} /> Releases</strong>
          <span>{formatDate(round.publishAt)}</span>
        </div>
      </div>
      {round.status === "open" && hasCapacity ? (
        <Link className="button" to={`/rounds/${round.id}/submit`}>
          Choose a track
        </Link>
      ) : round.status === "open" ? (
        <p className="round-capacity-note">You’ve used all {round.submissionLimit} submission{round.submissionLimit === 1 ? "" : "s"}. You can still replace or withdraw one below.</p>
      ) : (
        <p className="muted">Submissions are currently closed.</p>
      )}
      {round.seriesId && (
        <Link className="history-link" to={`/series/${round.seriesId}`}>
          View series history
        </Link>
      )}
    </section>
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
      <StatePanel kind="loading" title="Loading submissions">Checking what the group has shared so far.</StatePanel>
    );
  if (submissions.isError)
    return (
      <StatePanel kind="error" title="We couldn’t load submissions">Refresh the page to try again.</StatePanel>
    );
  const entries = submissions.data ?? [];
  return (
    <section className="panel submission-history" aria-labelledby="submissions-heading">
      <div className="section-heading">
        <div><p className="eyebrow">Shared so far</p><h2 id="submissions-heading">Submissions</h2></div>
        <span className="submission-count">{entries.filter((entry) => entry.status === "accepted").length} track{entries.filter((entry) => entry.status === "accepted").length === 1 ? "" : "s"}</span>
      </div>
      {entries.length === 0 ? (
        <StatePanel title="The playlist is waiting for its first track">Be the one to set the tone for this round.</StatePanel>
      ) : (
        <ul>
          {entries.map((entry) => (
            <li
              key={entry.id}
              className={entry.status === "withdrawn" ? "withdrawn" : ""}
            >
              {entry.track.artworkUrl && <img className="submission-artwork" src={entry.track.artworkUrl} alt="" />}
              <div>
                <strong>{entry.track.name}</strong>
                <span>
                  {entry.track.artist}
                  {entry.track.album ? ` · ${entry.track.album}` : ""}
                </span>
                <small>Submitted by {entry.contributor.displayName ?? "Unnamed member"}{entry.isMine ? " (you)" : ""}</small>
              </div>
              {entry.contributor.spotifyProfileImageUrl ? (
                <img className="contributor-avatar" src={entry.contributor.spotifyProfileImageUrl} alt={`${entry.contributor.displayName ?? "Contributor"}'s Spotify profile`} />
              ) : (
                <span className="contributor-avatar contributor-avatar-fallback" aria-label={`${entry.contributor.displayName ?? "Unnamed member"}'s profile`}>
                  {(entry.contributor.displayName ?? "?").slice(0, 1).toUpperCase()}
                </span>
              )}
              {entry.note && <p>{entry.note}</p>}
              {entry.isMine && entry.status === "accepted" && roundIsOpen && (
                <details>
                  <summary>Manage your submission</summary>
                  <form
                    onSubmit={(event) => {
                      event.preventDefault();
                      const form = new FormData(event.currentTarget);
                      onSaveNote(
                        entry.id,
                        String(form.get("note") || "").trim() || null,
                      );
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
                      <Link
                        to={`/rounds/${roundId}/submit?replace=${entry.id}`}
                      >
                        Replace track
                      </Link>
                      <button
                        type="button"
                        className="danger"
                        onClick={() => onWithdraw(entry)}
                      >
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
    queryKey: ["series", seriesId],
    queryFn: () => api<SeriesHistory>(`/series/${seriesId}`),
    enabled: Boolean(seriesId),
    retry: false,
  });
  if (series.isLoading) return <main className="shell narrow-page-shell"><StatePanel kind="loading" title="Loading series history">Collecting the rounds you can revisit.</StatePanel></main>;
  if (series.isError || !series.data)
    return (
      <main className="shell narrow-page-shell">
        <StatePanel kind="error" title="Series unavailable">You do not have access to this series. <Link to="/">Return to your series</Link></StatePanel>
      </main>
    );
  const item = series.data;
  return (
    <main className="shell">
      <Link className="back" to="/">
        ← Your series
      </Link>
      <section className="panel detail series-history-panel">
        <div className="series-page-heading"><div><p className="eyebrow">Series · {item.timezone}</p>
        <h1>{item.name}</h1>
        {item.description && <p>{item.description}</p>}</div>
        {item.isAdmin && <Link className="button button-secondary" to={`/admin/series/${item.id}`}>Manage series</Link>}</div>
        <p className="muted">A record of the rounds and releases your group has made together. Times shown in {item.timezone}.</p>
        {item.rounds.length === 0 && <StatePanel title="No rounds yet">When this series starts a round, it will appear here.</StatePanel>}
        {item.rounds[0] && <FeaturedRound round={item.rounds[0]} />}
        <div className="series-round-list">
          {item.rounds.slice(1).map((round) => (
            <article key={round.id}>
              <span className={`status ${round.status}`}>{round.status}</span>
              <div>
                <h2>{round.title}</h2>
                <p>
                  Opened {formatDate(round.opensAt)} · Published{" "}
                  {formatDate(round.publishAt)}
                </p>
              </div>
              <Link to={`/rounds/${round.id}`}>View round</Link>
            </article>
          ))}
        </div>
      </section>
    </main>
  );
}

function FeaturedRound({ round }: { round: SeriesHistory["rounds"][number] }) {
  const active = round.status !== "published";
  return (
    <article className="series-featured-round">
      <div><p className="eyebrow">{active ? "Current round" : "Latest release"}</p><h2>{round.title}</h2><p>{active ? `Closes ${formatDate(round.closesAt)}` : `Released ${formatDate(round.publishAt)}`}</p></div>
      <div><span className={`status ${round.status}`}>{round.status}</span><Link className="button" to={`/rounds/${round.id}`}>{active ? "Open round" : "Revisit round"}</Link></div>
    </article>
  );
}
