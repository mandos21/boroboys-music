import { Fragment, type CSSProperties } from "react";
import { useQuery } from "@tanstack/react-query";

import { api } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import type { components } from "../../api/schema";
import { StatePanel } from "../../components/ui/StatePanel";
import { Tooltip, TooltipContent, TooltipTrigger } from "../../components/ui/tooltip";
import { avatarStyle } from "../../lib/avatar";
import "./attribution.css";
import { ContributorAvatar } from "./ContributorAvatar";
import { joinNames } from "./joinNames";
import type { AttributionSubmitterBreakdown } from "./types";

type Contributor = components["schemas"]["ContributorResponse"];

type MatrixCell = {
  count: number;
  guessers: Contributor[];
};

type Matrix = {
  people: Contributor[];
  cells: MatrixCell[][];
  maxCorrect: number;
  maxMistake: number;
};

/** Rows are who actually submitted, columns are who a guess named - the same
 * breakdown data as the "by person" list, just sliced the other way: every
 * (actual, guessed) pair in the round at once instead of one person at a time. */
function buildMatrix(breakdown: AttributionSubmitterBreakdown[]): Matrix {
  const people = breakdown.map((entry) => entry.contributor);
  const indexById = new Map(people.map((person, index) => [person.id, index]));
  const cells: MatrixCell[][] = people.map(() => people.map(() => ({ count: 0, guessers: [] })));

  for (const entry of breakdown) {
    const rowIndex = indexById.get(entry.contributor.id);
    if (rowIndex === undefined) continue;
    for (const song of entry.songs) {
      for (const guess of song.guesses) {
        const colIndex = indexById.get(guess.guessedContributor.id);
        if (colIndex === undefined) continue;
        const cell = cells[rowIndex][colIndex];
        cell.count += 1;
        cell.guessers.push(guess.guesser);
      }
    }
  }

  let maxCorrect = 0;
  let maxMistake = 0;
  people.forEach((_, rowIndex) => {
    people.forEach((_, colIndex) => {
      const count = cells[rowIndex][colIndex].count;
      if (rowIndex === colIndex) maxCorrect = Math.max(maxCorrect, count);
      else maxMistake = Math.max(maxMistake, count);
    });
  });

  return { people, cells, maxCorrect, maxMistake };
}

function MatrixSwatch({ index, person }: { index: number; person: Contributor }) {
  return (
    <span
      className="contributor-avatar-fallback attribution-matrix-swatch"
      style={avatarStyle(person.displayName)}
      aria-hidden="true"
    >
      {index + 1}
    </span>
  );
}

function ColumnHeader({ person, index }: { person: Contributor; index: number }) {
  return (
    <Tooltip>
      <TooltipTrigger className="attribution-matrix-header" aria-label={person.displayName}>
        <span className="attribution-matrix-header-full">
          <ContributorAvatar member={person} />
        </span>
        <span className="attribution-matrix-header-compact">
          <MatrixSwatch index={index} person={person} />
        </span>
      </TooltipTrigger>
      <TooltipContent role="tooltip">{person.displayName}</TooltipContent>
    </Tooltip>
  );
}

function RowHeader({ person, index }: { person: Contributor; index: number }) {
  return (
    <div className="attribution-matrix-row-header">
      <span className="attribution-matrix-header-full">
        <ContributorAvatar member={person} />
        <span>{person.displayName}</span>
      </span>
      <span className="attribution-matrix-header-compact">
        <MatrixSwatch index={index} person={person} />
      </span>
    </div>
  );
}

function MatrixCellButton({
  cell,
  actual,
  guessed,
  heat,
}: {
  cell: MatrixCell;
  actual: Contributor;
  guessed: Contributor;
  heat: number;
}) {
  if (cell.count === 0) {
    return <div className="attribution-matrix-cell empty" aria-hidden="true" />;
  }
  const isDiagonal = actual.id === guessed.id;
  const heavy = heat > 0.5;
  const names = joinNames(cell.guessers.map((guesser) => guesser.displayName));
  const description = isDiagonal
    ? `${names} correctly guessed ${actual.displayName}`
    : `${names} guessed ${actual.displayName}'s songs were ${guessed.displayName}'s`;
  return (
    <Tooltip>
      <TooltipTrigger
        className={`attribution-matrix-cell${isDiagonal ? " correct" : " incorrect"}${heavy ? " heavy" : ""}`}
        style={{ "--heat": heat } as CSSProperties}
        aria-label={description}
      >
        {cell.count}
      </TooltipTrigger>
      <TooltipContent role="tooltip">{description}</TooltipContent>
    </Tooltip>
  );
}

/** A confusion matrix: every guess in the round at once, who it was really by
 * down the rows and who it was guessed to be across the columns. Complements
 * "by person" rather than replacing it - this is the shape for spotting
 * which pairs of people the group mixed up most, all in one glance. */
export function AttributionMatrix({ roundId, enabled }: { roundId: string; enabled: boolean }) {
  const breakdown = useQuery({
    queryKey: queryKeys.attributionBreakdown(roundId),
    queryFn: () => api<AttributionSubmitterBreakdown[]>(`/rounds/${roundId}/attribution/breakdown`),
    enabled,
    retry: false,
  });

  if (!enabled) return null;

  const matrix = breakdown.data ? buildMatrix(breakdown.data) : null;

  return (
    <section
      id="round-matrix"
      className="panel attribution-matrix"
      aria-labelledby="attribution-matrix-heading"
    >
      <div className="section-heading">
        <div>
          <p className="eyebrow">Guess Who?</p>
          <h2 id="attribution-matrix-heading">Who got mixed up with who</h2>
        </div>
      </div>
      {breakdown.isLoading && (
        <StatePanel kind="loading" title="Loading the matrix">
          Tallying up every guess in the round.
        </StatePanel>
      )}
      {breakdown.isError && (
        <StatePanel kind="error" title="Couldn’t load this">
          Try again in a moment.
        </StatePanel>
      )}
      {matrix && matrix.people.length > 0 && (
        <>
          <p className="attribution-matrix-caption">
            Rows are who actually submitted, columns are who a guess named.
          </p>
          <ul className="attribution-matrix-legend">
            {matrix.people.map((person, index) => (
              <li key={person.id}>
                <MatrixSwatch index={index} person={person} />
                <ContributorAvatar member={person} />
                <span>{person.displayName}</span>
              </li>
            ))}
          </ul>
          <div
            className="attribution-matrix-grid"
            style={{ gridTemplateColumns: `auto repeat(${matrix.people.length}, 1fr)` }}
          >
            <div className="attribution-matrix-corner" aria-hidden="true" />
            {matrix.people.map((person, index) => (
              <ColumnHeader key={person.id} person={person} index={index} />
            ))}
            {matrix.people.map((rowPerson, rowIndex) => (
              <Fragment key={rowPerson.id}>
                <RowHeader person={rowPerson} index={rowIndex} />
                {matrix.people.map((colPerson, colIndex) => {
                  const cell = matrix.cells[rowIndex][colIndex];
                  const isDiagonal = rowIndex === colIndex;
                  const max = isDiagonal ? matrix.maxCorrect : matrix.maxMistake;
                  const heat = max === 0 ? 0 : cell.count / max;
                  return (
                    <MatrixCellButton
                      key={colPerson.id}
                      cell={cell}
                      actual={rowPerson}
                      guessed={colPerson}
                      heat={heat}
                    />
                  );
                })}
              </Fragment>
            ))}
          </div>
        </>
      )}
    </section>
  );
}
