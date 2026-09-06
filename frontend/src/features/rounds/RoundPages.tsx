import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router";

import { api, patch, post } from "../../api/client";
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
  contributor: { id: string; displayName: string | null };
  track: { name: string; artist: string; album: string | null };
};

type SeriesHistory = {
  id: string;
  name: string;
  description: string | null;
  timezone: string;
  rounds: Array<
    Pick<Round, "id" | "title" | "status" | "opensAt" | "publishAt">
  >;
};

export function RoundPage() {
  const { roundId } = useParams();
  const queryClient = useQueryClient();
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
  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ["round-submissions", roundId] });
  const withdraw = useMutation({
    mutationFn: (submissionId: string) =>
      post<void>(`/rounds/submissions/${submissionId}/withdraw`, undefined),
    onSuccess: invalidate,
  });
  const updateNote = useMutation({
    mutationFn: ({
      submissionId,
      note,
    }: {
      submissionId: string;
      note: string | null;
    }) => patch<void>(`/rounds/submissions/${submissionId}`, { note }),
    onSuccess: invalidate,
  });

  if (round.isLoading)
    return (
      <main className="shell">
        <p>Loading round…</p>
      </main>
    );
  if (round.isError || !round.data) return <UnavailableRound />;

  const item = round.data;
  return (
    <main className="shell">
      <Link className="back" to="/">
        ← Your rounds
      </Link>
      <RoundOverview round={item} />
      <RoundSubmissions
        roundId={item.id}
        submissions={submissions}
        roundIsOpen={item.status === "open"}
        onWithdraw={withdraw.mutate}
        onSaveNote={(id, note) => updateNote.mutate({ submissionId: id, note })}
      />
    </main>
  );
}

function UnavailableRound() {
  return (
    <main className="shell">
      <section className="panel">
        <h1>Round unavailable</h1>
        <p>You may no longer be a contributor in this round.</p>
        <Link to="/">Return to your rounds</Link>
      </section>
    </main>
  );
}

function RoundOverview({ round }: { round: Round }) {
  return (
    <section className="panel detail">
      <span className={`status ${round.status}`}>{round.status}</span>
      <h1>{round.title}</h1>
      <p>Submit up to {round.submissionLimit} tracks during this round.</p>
      <div className="timeline">
        <div>
          <strong>Opens</strong>
          <span>{formatDate(round.opensAt)}</span>
        </div>
        <div>
          <strong>Closes</strong>
          <span>{formatDate(round.closesAt)}</span>
        </div>
        <div>
          <strong>Published</strong>
          <span>{formatDate(round.publishAt)}</span>
        </div>
      </div>
      {round.status === "open" ? (
        <Link className="button" to={`/rounds/${round.id}/submit`}>
          Choose a track
        </Link>
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
  onWithdraw: (id: string) => void;
  onSaveNote: (id: string, note: string | null) => void;
}) {
  if (submissions.isLoading)
    return (
      <section className="panel">
        <p>Loading submissions…</p>
      </section>
    );
  if (submissions.isError)
    return (
      <section className="panel">
        <p role="alert">Submissions could not be loaded.</p>
      </section>
    );
  const entries = submissions.data ?? [];
  return (
    <section className="panel submission-history">
      <h2>Submissions</h2>
      {entries.length === 0 ? (
        <p>No tracks have been submitted yet.</p>
      ) : (
        <ul>
          {entries.map((entry) => (
            <li
              key={entry.id}
              className={entry.status === "withdrawn" ? "withdrawn" : ""}
            >
              <div>
                <strong>{entry.track.name}</strong>
                <span>
                  {entry.track.artist}
                  {entry.track.album ? ` · ${entry.track.album}` : ""}
                </span>
                <small>
                  {entry.isMine
                    ? "Your submission"
                    : (entry.contributor.displayName ?? "A contributor")}
                </small>
              </div>
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
                        onClick={() => onWithdraw(entry.id)}
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
  if (series.isLoading)
    return (
      <main className="shell">
        <p>Loading series history…</p>
      </main>
    );
  if (series.isError || !series.data)
    return (
      <main className="shell">
        <section className="panel">
          <h1>Series unavailable</h1>
          <p>You do not have access to this series.</p>
          <Link to="/">Return to your rounds</Link>
        </section>
      </main>
    );
  const item = series.data;
  return (
    <main className="shell">
      <Link className="back" to="/">
        ← Your rounds
      </Link>
      <section className="panel detail">
        <p className="eyebrow">Series history</p>
        <h1>{item.name}</h1>
        {item.description && <p>{item.description}</p>}
        <p className="muted">Times shown in {item.timezone}.</p>
        <div className="series-round-list">
          {item.rounds.map((round) => (
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
