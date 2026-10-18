import { Link } from "react-router";

import "./attribution-results.css";
import { ContributorAvatar } from "./ContributorAvatar";
import type { AttributionLeaderboardEntry } from "./types";

export function AttributionLeaderboard({
  entries = [],
}: {
  entries: AttributionLeaderboardEntry[] | undefined;
}) {
  if (entries.length === 0) return null;
  return (
    <section
      id="round-leaderboard"
      className="panel attribution-leaderboard"
      aria-labelledby="attribution-leaderboard-heading"
    >
      <div className="section-heading">
        <div>
          <p className="eyebrow">Guess Who?</p>
          <h2 id="attribution-leaderboard-heading">Leaderboard</h2>
        </div>
      </div>
      <ol>
        {entries.map((entry) => {
          const percent =
            entry.totalCount === 0
              ? null
              : Math.round((entry.correctCount / entry.totalCount) * 100);
          return (
            <li key={entry.contributor.id}>
              <span className="attribution-leaderboard-rank" aria-hidden="true">
                {entries.findIndex(
                  (other) =>
                    (other.totalCount === 0 ? 0 : other.correctCount / other.totalCount) ===
                    (entry.totalCount === 0 ? 0 : entry.correctCount / entry.totalCount),
                ) + 1}
              </span>
              <Link
                className="attribution-leaderboard-contributor"
                to={`/people/${entry.contributor.id}`}
              >
                <ContributorAvatar member={entry.contributor} />
                <span>{entry.contributor.displayName}</span>
              </Link>
              <strong>{percent === null ? "—" : `${percent}%`}</strong>
              <small>
                {entry.correctCount}/{entry.totalCount}
              </small>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
