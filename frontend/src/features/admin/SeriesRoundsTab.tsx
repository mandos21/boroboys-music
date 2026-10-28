import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { api } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import { Disclosure } from "../../components/ui/Disclosure";
import { formatDate } from "../../lib/format";
import { RoundScheduleForm } from "./RoundScheduleForm";
import { SeriesRoundSettings } from "./SeriesRoundSettings";
import { SuccessorPlanEditor } from "./SuccessorPlanEditor";
import type { Connection, Round, SeriesDetail, User } from "./types";

export const isPastRound = (round: Round) => ["published", "cancelled"].includes(round.status);

export function SeriesRoundList({ rounds, empty }: { rounds: Round[]; empty: string }) {
  return rounds.length ? (
    <div className="admin-items">
      {rounds.map((round) => (
        <article key={round.id}>
          <div>
            <span className={`status ${round.status}`}>{round.status}</span>
            <strong>{round.title}</strong>
            <span>
              Opens {formatDate(round.opensAt)} · closes {formatDate(round.closesAt)}
            </span>
          </div>
          <Link to={`/admin/rounds/${round.id}`}>Manage round</Link>
        </article>
      ))}
    </div>
  ) : (
    <p className="field-hint">{empty}</p>
  );
}

export function SeriesRoundsTab({
  series,
  active,
  onSaved,
}: {
  series: SeriesDetail;
  active: boolean;
  onSaved: () => void;
}) {
  const members = useQuery({
    queryKey: queryKeys.seriesMembers(series.id),
    queryFn: () => api<User[]>(`/admin/series/${series.id}/members`),
    enabled: active,
  });
  const connections = useQuery({
    queryKey: queryKeys.connections(),
    queryFn: () => api<Connection[]>("/connections"),
    enabled: active,
  });
  return (
    <div className="series-tab-stack">
      <SeriesRoundSettings series={series} onSaved={onSaved} />
      <section className="panel" aria-labelledby="current-rounds-heading">
        <h2 id="current-rounds-heading">Current and upcoming rounds</h2>
        <p className="field-hint">
          Manage a round, schedule the next one, or let automation take care of it.
        </p>
        <SeriesRoundList
          rounds={series.rounds.filter((round) => !isPastRound(round))}
          empty="No active rounds. Schedule one below to get started."
        />
        <div className="series-round-controls">
          <Disclosure
            keepMounted
            title="Schedule a round"
            description="Choose the dates, prompt, and contributors for a new round."
          >
            {members.isError || connections.isError ? (
              <p role="alert">Couldn’t load scheduling options. Refresh to try again.</p>
            ) : members.isPending || connections.isPending ? (
              <p role="status">Loading scheduling options…</p>
            ) : (
              <RoundScheduleForm
                series={series}
                members={members.data}
                spotifyAccounts={connections.data.filter(
                  (account) => account.provider === "spotify" && account.isActive,
                )}
                onScheduled={onSaved}
              />
            )}
          </Disclosure>
          <Disclosure
            keepMounted
            title="Round automation"
            description={
              series.autoStartNextRound && series.roundPlan
                ? "On · The next round is created after publication."
                : "Off · Rounds are scheduled manually."
            }
          >
            <SuccessorPlanEditor series={series} onSaved={onSaved} />
          </Disclosure>
        </div>
      </section>
    </div>
  );
}
