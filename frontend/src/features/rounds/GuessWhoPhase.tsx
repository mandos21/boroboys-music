import { useQuery } from "@tanstack/react-query";

import { api } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import type { AttributionStatus } from "../attribution/types";

/** The phase is viewer-specific: completing guesses reveals answers early. */
export function GuessWhoPhase({ roundId }: { roundId: string }) {
  const attribution = useQuery({
    queryKey: queryKeys.attribution(roundId),
    queryFn: () => api<AttributionStatus>(`/rounds/${roundId}/attribution`),
    retry: false,
    refetchInterval: (query) => {
      const phase = query.state.data;
      return phase?.enabled &&
        phase.published &&
        phase.revealAt &&
        new Date(phase.revealAt).getTime() > Date.now()
        ? 60_000
        : false;
    },
  });
  const status = attribution.data;
  if (!status?.enabled || !status.published || !status.revealAt) return null;
  if (new Date(status.revealAt).getTime() <= attribution.dataUpdatedAt) return null;
  return (
    <span className="guess-who-phase">
      {status.revealed ? "Guess Who? See results" : "Guess Who? Make your picks"}
    </span>
  );
}
