import { useQuery } from "@tanstack/react-query";
import { ChevronDown, Disc3 } from "lucide-react";

import { api } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "../../components/ui/collapsible";
import { StatePanel } from "../../components/ui/StatePanel";
import { Tooltip, TooltipContent, TooltipTrigger } from "../../components/ui/tooltip";
import "./attribution.css";
import { ContributorAvatar } from "./ContributorAvatar";
import { joinNames } from "./joinNames";
import type {
  AttributionSongBreakdown,
  AttributionSongGuess,
  AttributionSubmitterBreakdown,
} from "./types";

function groupAccuracyLabel(correct: number, total: number) {
  return total === 0 ? "No guesses yet" : `${Math.round((correct / total) * 100)}% as a group`;
}

type MistakenGroup = {
  target: AttributionSongGuess["guessedContributor"];
  guessers: AttributionSongGuess["guesser"][];
};

function groupMistakenGuesses(guesses: AttributionSongGuess[]): MistakenGroup[] {
  const groups = new Map<string, MistakenGroup>();
  for (const guess of guesses) {
    if (guess.isCorrect) continue;
    const group = groups.get(guess.guessedContributor.id);
    if (group) {
      group.guessers.push(guess.guesser);
    } else {
      groups.set(guess.guessedContributor.id, {
        target: guess.guessedContributor,
        guessers: [guess.guesser],
      });
    }
  }
  return [...groups.values()];
}

function SongRow({ song }: { song: AttributionSongBreakdown }) {
  const correctGuesses = song.guesses.filter((guess) => guess.isCorrect);
  const mistakenGroups = groupMistakenGuesses(song.guesses);

  return (
    <li className="attribution-breakdown-song">
      {song.track.artworkUrl ? (
        <img src={song.track.artworkUrl} alt="" />
      ) : (
        <span className="attribution-track-chip-placeholder" aria-hidden="true">
          <Disc3 size={16} />
        </span>
      )}
      <div className="attribution-breakdown-track">
        <strong>{song.track.name}</strong>
        <small>{song.track.artist}</small>
      </div>
      <small className="attribution-breakdown-song-stat">
        {song.groupTotalCount === 0
          ? "No guesses"
          : `${song.groupCorrectCount}/${song.groupTotalCount} correct`}
      </small>
      <div className="attribution-breakdown-guess-groups">
        {correctGuesses.length > 0 && (
          <div className="attribution-breakdown-guess-group">
            <small className="attribution-breakdown-guess-group-label">Correctly guessed by</small>
            <div className="attribution-breakdown-guessers">
              {correctGuesses.map((guess) => (
                <Tooltip key={guess.guesser.id}>
                  <TooltipTrigger
                    className="attribution-breakdown-guesser correct"
                    aria-label={`${guess.guesser.displayName} guessed correctly`}
                  >
                    <ContributorAvatar member={guess.guesser} />
                  </TooltipTrigger>
                  <TooltipContent role="tooltip">
                    {guess.guesser.displayName} guessed correctly
                  </TooltipContent>
                </Tooltip>
              ))}
            </div>
          </div>
        )}
        {mistakenGroups.length > 0 && (
          <div className="attribution-breakdown-guess-group">
            <small className="attribution-breakdown-guess-group-label">Mistaken for</small>
            <div className="attribution-breakdown-guessers">
              {mistakenGroups.map((group) => {
                const names = joinNames(group.guessers.map((guesser) => guesser.displayName));
                return (
                  <Tooltip key={group.target.id}>
                    <TooltipTrigger
                      className="attribution-breakdown-guesser incorrect attribution-breakdown-mistaken-chip"
                      aria-label={`${names} guessed ${group.target.displayName}`}
                    >
                      <ContributorAvatar member={group.target} />
                      {group.guessers.length > 1 && (
                        <span className="attribution-breakdown-guess-count" aria-hidden="true">
                          {group.guessers.length}
                        </span>
                      )}
                    </TooltipTrigger>
                    <TooltipContent role="tooltip">
                      {names} guessed {group.target.displayName}
                    </TooltipContent>
                  </Tooltip>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </li>
  );
}

function SubmitterSection({
  entry,
  defaultOpen,
}: {
  entry: AttributionSubmitterBreakdown;
  defaultOpen: boolean;
}) {
  return (
    <Collapsible className="attribution-breakdown-entry" defaultOpen={defaultOpen}>
      <CollapsibleTrigger className="attribution-breakdown-trigger">
        <ContributorAvatar member={entry.contributor} />
        <span className="attribution-breakdown-name">{entry.contributor.displayName}</span>
        <span className="attribution-breakdown-stats">
          {entry.yourTotalCount !== null && entry.yourCorrectCount !== null && (
            <span className="attribution-breakdown-your-stat">
              You: {entry.yourCorrectCount}/{entry.yourTotalCount}
            </span>
          )}
          <span className="attribution-breakdown-group-stat">
            {groupAccuracyLabel(entry.groupCorrectCount, entry.groupTotalCount)}
          </span>
        </span>
        <ChevronDown aria-hidden="true" size={17} />
      </CollapsibleTrigger>
      <CollapsibleContent className="attribution-breakdown-content">
        <ul className="attribution-breakdown-songs">
          {entry.songs.map((song) => (
            <SongRow key={song.submissionId} song={song} />
          ))}
        </ul>
      </CollapsibleContent>
    </Collapsible>
  );
}

/** Who submitted what and who guessed who, grouped by submitter rather than
 * by guesser - the group's collective read on each person, song by song. */
export function AttributionBreakdown({
  roundId,
  viewerId,
  enabled,
}: {
  roundId: string;
  viewerId: string | undefined;
  enabled: boolean;
}) {
  const breakdown = useQuery({
    queryKey: queryKeys.attributionBreakdown(roundId),
    queryFn: () => api<AttributionSubmitterBreakdown[]>(`/rounds/${roundId}/attribution/breakdown`),
    enabled,
    retry: false,
  });

  if (!enabled) return null;

  return (
    <section
      className="panel attribution-breakdown"
      aria-labelledby="attribution-breakdown-heading"
    >
      <div className="section-heading">
        <div>
          <p className="eyebrow">Guess Who?</p>
          <h2 id="attribution-breakdown-heading">By person</h2>
        </div>
      </div>
      {breakdown.isLoading && (
        <StatePanel kind="loading" title="Loading the breakdown">
          Tallying up who guessed what.
        </StatePanel>
      )}
      {breakdown.isError && (
        <StatePanel kind="error" title="Couldn’t load this">
          Try again in a moment.
        </StatePanel>
      )}
      {breakdown.data && (
        <ul className="attribution-breakdown-list">
          {breakdown.data.map((entry) => (
            <li key={entry.contributor.id}>
              <SubmitterSection entry={entry} defaultOpen={entry.contributor.id === viewerId} />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
