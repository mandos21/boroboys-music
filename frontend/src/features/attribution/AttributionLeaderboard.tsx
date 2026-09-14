import { Link } from "react-router";

import "./attribution.css";
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
        {entries.map((entry, index) => {
          const percent =
            entry.totalCount === 0
              ? 100
              : Math.round((entry.correctCount / entry.totalCount) * 100);
          return (
            <li key={entry.contributor.id}>
              <span className="attribution-leaderboard-rank" aria-hidden="true">
                {index + 1}
              </span>
              <Link
                className="attribution-leaderboard-contributor"
                to={`/people/${entry.contributor.id}`}
              >
                <ContributorAvatar member={entry.contributor} />
                <span>{entry.contributor.displayName}</span>
              </Link>
              <strong>{percent}%</strong>
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
