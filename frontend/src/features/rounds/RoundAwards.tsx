import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";

import { api } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import type { components } from "../../api/schema";
import { ContributorAvatar } from "../attribution/ContributorAvatar";
import "../attribution/attribution-results.css";

type Award = components["schemas"]["RoundAwardResponse"];

export function RoundAwards({ roundId }: { roundId: string }) {
  const awards = useQuery({
    queryKey: queryKeys.roundAwards(roundId),
    queryFn: () => api<Award[]>(`/rounds/${roundId}/awards`),
    refetchInterval: 300_000,
    retry: false,
  });
  if (!awards.data?.length) return null;
  return (
    <section className="panel round-awards-section" aria-labelledby="round-awards-heading">
      <div className="section-heading">
        <div>
          <p className="eyebrow">The round</p>
          <h2 id="round-awards-heading">Superlatives</h2>
        </div>
      </div>
      <div className="attribution-awards" aria-label="Round awards">
        {awards.data.map((award) => (
          <article className={`attribution-award ${award.variant}`} key={award.title}>
            <h3>{award.title}</h3>
            <p>{award.detail}</p>
            <div className="attribution-award-winners">
              <Link to={`/people/${award.contributor.id}`}>
                <ContributorAvatar member={award.contributor} />
                <span>{award.contributor.displayName}</span>
              </Link>
            </div>
            <strong>{award.explanation}</strong>
          </article>
        ))}
      </div>
    </section>
  );
}
