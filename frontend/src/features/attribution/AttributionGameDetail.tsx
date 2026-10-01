import { useQuery } from "@tanstack/react-query";
import { Check, Disc3, X } from "lucide-react";

import { api } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import { Sheet, SheetClose, SheetContent, SheetTitle } from "../../components/ui/sheet";
import { StatePanel } from "../../components/ui/StatePanel";
import "./attribution.css";
import { ContributorAvatar } from "./ContributorAvatar";
import type { AttributionGameDetail } from "./types";

/** A reviewable record of one player's finished game - a plain, scannable
 * list of track/guessed/actual, not the dramatic one-time flip-card reveal. */
export function AttributionGameDetailSheet({
  roundId,
  userId,
  onOpenChange,
}: {
  roundId: string;
  userId: string | null;
  onOpenChange: (open: boolean) => void;
}) {
  const detail = useQuery({
    queryKey: queryKeys.attributionGameDetail(roundId, userId ?? undefined),
    queryFn: () => api<AttributionGameDetail>(`/rounds/${roundId}/attribution/games/${userId}`),
    enabled: userId !== null,
    retry: false,
  });

  return (
    <Sheet open={userId !== null} onOpenChange={onOpenChange}>
      <SheetContent className="attribution-detail-sheet" aria-label="Guessed answers">
        <div className="attribution-detail-heading">
          <SheetTitle>
            {detail.data ? `${detail.data.contributor.displayName}'s answers` : "Answers"}
          </SheetTitle>
          <SheetClose className="icon-button" aria-label="Close">
            ×
          </SheetClose>
        </div>
        {detail.isLoading && (
          <StatePanel kind="loading" title="Loading answers">
            Finding what they guessed.
          </StatePanel>
        )}
        {detail.isError && (
          <StatePanel kind="error" title="Couldn’t load this">
            Try again in a moment.
          </StatePanel>
        )}
        {detail.data && (
          <>
            <p className="attribution-detail-summary">
              <strong>
                {detail.data.correctCount} / {detail.data.totalCount}
              </strong>
              correct
            </p>
            <ul className="attribution-detail-list">
              {detail.data.items.map((item) => (
                <li key={item.submissionId} className={item.isCorrect ? "correct" : "incorrect"}>
                  {item.track.artworkUrl ? (
                    <img src={item.track.artworkUrl} alt="" />
                  ) : (
                    <span className="attribution-track-chip-placeholder" aria-hidden="true">
                      <Disc3 size={16} />
                    </span>
                  )}
                  <div className="attribution-detail-track">
                    <strong>{item.track.name}</strong>
                    <small>{item.track.artist}</small>
                  </div>
                  <div className="attribution-detail-guess">
                    <ContributorAvatar member={item.guessedContributor} />
                    <span>{item.guessedContributor.displayName}</span>
                  </div>
                  <div className="attribution-detail-actual">
                    <ContributorAvatar member={item.actualContributor} />
                    <span>{item.actualContributor.displayName}</span>
                  </div>
                  <span className="attribution-detail-mark" aria-hidden="true">
                    {item.isCorrect ? <Check size={16} /> : <X size={16} />}
                  </span>
                  <span className="sr-only">
                    {item.isCorrect
                      ? `Correct: ${item.actualContributor.displayName}`
                      : `Guessed ${item.guessedContributor.displayName}, actually ${item.actualContributor.displayName}`}
                  </span>
                </li>
              ))}
            </ul>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}
