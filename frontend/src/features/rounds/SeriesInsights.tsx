import { useLayoutEffect, useRef, useState, type CSSProperties, type RefObject } from "react";
import { ChevronDown } from "lucide-react";

import type { components } from "../../api/schema";
import { InfoHint } from "../../components/ui/InfoHint";
import { GenreGroupBar } from "../genres/GenreGroupBar";
import { GenrePill } from "../genres/GenrePill";
import { genreGroupClass, genreGroupTotals, type Genre, type GenreGroup } from "../genres/genre";
import "../genres/genres.css";
import "./seriesInsights.css";

type SeriesStats = components["schemas"]["SeriesGenreInsightsResponse"];
type Contributor = SeriesStats["contributors"][number];
type ContributorMix = { contributor: Contributor; groups: GenreGroup[]; total: number };
type ActiveSelection =
  | { kind: "contributor"; contributorId: string }
  | { kind: "group"; group: string }
  | { kind: "genre"; genreName: string }
  | null;

const COLLAPSED_GENRE_LIMIT = 32;

export function SeriesInsights({ stats }: { stats: SeriesStats }) {
  const [expanded, setExpanded] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [selection, setSelection] = useState<ActiveSelection>(null);
  const genreItemsRef = useRef<HTMLDivElement>(null);
  const mixItemsRef = useRef<HTMLDivElement>(null);
  const activeSelection = currentSelection(selection, stats);
  const selectedContributor =
    activeSelection?.kind === "contributor"
      ? stats.contributors.find((contributor) => contributor.id === activeSelection.contributorId)
      : undefined;
  const groups = genreGroupTotals(stats.genreSpread);
  const hasDeferredGenres = stats.genreSpread.length > COLLAPSED_GENRE_LIMIT;

  useLayoutEffect(() => {
    if (expanded) return;
    const items = [genreItemsRef.current, mixItemsRef.current].filter(
      (item): item is HTMLDivElement => item !== null,
    );
    const measure = () =>
      setHasMore(
        hasDeferredGenres || items.some((item) => item.scrollHeight > item.clientHeight + 1),
      );
    measure();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(measure);
    items.forEach((item) => observer.observe(item));
    return () => observer.disconnect();
  }, [expanded, hasDeferredGenres, stats.contributors, stats.genreSpread]);

  const toggleExpanded = () => {
    setExpanded((value) => {
      if (value) resetScrollPositions(genreItemsRef, mixItemsRef);
      return !value;
    });
  };
  const selectContributor = (contributorId: string) => {
    setSelection((current) =>
      current?.kind === "contributor" && current.contributorId === contributorId
        ? null
        : { kind: "contributor", contributorId },
    );
    resetScrollPosition(genreItemsRef);
  };
  const selectGroup = (group: string) => {
    setSelection((current) =>
      current?.kind === "group" && current.group === group ? null : { kind: "group", group },
    );
    resetScrollPosition(mixItemsRef);
  };
  const selectGenre = (genreName: string) => {
    setSelection((current) =>
      current?.kind === "genre" && current.genreName === genreName
        ? null
        : { kind: "genre", genreName },
    );
    resetScrollPosition(mixItemsRef);
  };

  return (
    <section
      className={`series-insights${hasMore ? " has-more" : ""}${expanded ? " is-expanded" : ""}`}
      aria-label="What this series listens to"
    >
      <SeriesGenreSplit groups={groups} selection={activeSelection} onSelectGroup={selectGroup} />
      <div className="series-insights-grid">
        <SeriesGenres
          stats={stats}
          expanded={expanded}
          hasMore={hasMore}
          maxGenres={expanded ? undefined : COLLAPSED_GENRE_LIMIT}
          itemsRef={genreItemsRef}
          selection={activeSelection}
          selectedContributor={selectedContributor}
          onSelectGenre={selectGenre}
        />
        <SeriesGenreMix
          contributors={stats.contributors}
          expanded={expanded}
          hasMore={hasMore}
          itemsRef={mixItemsRef}
          selection={activeSelection}
          groups={groups}
          onSelectContributor={selectContributor}
          onSelectGroup={selectGroup}
        />
        {hasMore && (
          <button
            className="series-insight-toggle"
            type="button"
            aria-expanded={expanded}
            onClick={toggleExpanded}
          >
            {expanded ? "Less detail" : "More detail"}
            <ChevronDown aria-hidden="true" size={14} />
          </button>
        )}
      </div>
    </section>
  );
}

function SeriesGenres({
  stats,
  expanded,
  hasMore,
  maxGenres,
  itemsRef,
  selection,
  selectedContributor,
  onSelectGenre,
}: {
  stats: SeriesStats;
  expanded: boolean;
  hasMore: boolean;
  maxGenres: number | undefined;
  itemsRef: RefObject<HTMLDivElement | null>;
  selection: ActiveSelection;
  selectedContributor: Contributor | undefined;
  onSelectGenre: (genreName: string) => void;
}) {
  const genres = stats.genreSpread
    .map((genre, index) => ({
      genre,
      index,
      matches: genreMatchesSelection(genre, selection, selectedContributor),
    }))
    .sort(
      (left, right) => Number(right.matches) - Number(left.matches) || left.index - right.index,
    );
  return (
    <section
      className={`panel profile-chart series-insight-panel series-genre-fingerprint${expanded ? " is-expanded" : ""}`}
    >
      <div className="profile-chart-heading">
        <div>
          <p className="eyebrow">Genre fingerprint</p>
          <h2>What this series leans on</h2>
        </div>
        <span className="series-insight-stat">
          {selectedContributor
            ? `${selectedContributor.genres.length} unique tags`
            : `${stats.genreTaggedTrackCount} of ${stats.uniqueTrackCount} tracks tagged`}
        </span>
      </div>
      <div className={`series-insight-content${hasMore ? " has-more" : ""}`}>
        <div className="series-insight-items" ref={itemsRef}>
          <div className="genre-cloud series-genre-cloud">
            {genres.slice(0, maxGenres).map(({ genre, matches }) => (
              <GenrePill
                genre={genre}
                key={genre.name}
                highlighted={matches}
                muted={Boolean(selection && !matches)}
                selected={selection?.kind === "genre" && selection.genreName === genre.name}
                onSelect={() => onSelectGenre(genre.name)}
              />
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

function SeriesGenreMix({
  contributors,
  expanded,
  hasMore,
  itemsRef,
  selection,
  groups,
  onSelectContributor,
  onSelectGroup,
}: {
  contributors: SeriesStats["contributors"];
  expanded: boolean;
  hasMore: boolean;
  itemsRef: RefObject<HTMLDivElement | null>;
  selection: ActiveSelection;
  groups: GenreGroup[];
  onSelectContributor: (contributorId: string) => void;
  onSelectGroup: (group: string) => void;
}) {
  const tagged = contributors
    .map((contributor) => {
      const groups = genreGroupTotals(contributor.genres);
      return {
        contributor,
        groups,
        total: groups.reduce((sum, group) => sum + group.count, 0),
      };
    })
    .filter((item) => item.groups.length > 0)
    .sort((left, right) => {
      const leftCount = contributorTagCount(left, selection);
      const rightCount = contributorTagCount(right, selection);
      const leftTotal = contributorTagCount(left, null);
      const rightTotal = contributorTagCount(right, null);
      return (
        rightCount - leftCount ||
        rightTotal - leftTotal ||
        left.contributor.displayName.localeCompare(right.contributor.displayName)
      );
    });
  const selectedContributor =
    selection?.kind === "contributor"
      ? tagged.find((item) => item.contributor.id === selection.contributorId)?.contributor
      : undefined;
  return (
    <section
      className={`panel profile-chart series-insight-panel series-genre-mix${expanded ? " is-expanded" : ""}`}
    >
      <div className="profile-chart-heading">
        <div>
          <p className="eyebrow">The group</p>
          <h2>Who brings what</h2>
        </div>
        <span className="series-insight-stat">
          {mixHeading(selection, selectedContributor)}
          <InfoHint label="How the group genre mix works">
            Each bar is built from cached Spotify artist tags on that person&apos;s submissions.
            Select a person, genre family, or genre to compare what they bring to the series.
          </InfoHint>
        </span>
      </div>
      {tagged.length === 0 ? (
        <p className="profile-chart-empty">
          No genre tags have been cached for this series&apos; picks yet.
        </p>
      ) : (
        <>
          <ul className="genre-mix-key" aria-label="Genre colour key">
            {groups.map((group) => (
              <li key={group.group}>
                <button
                  type="button"
                  className={genreGroupClass(group.group)}
                  aria-pressed={selection?.kind === "group" && selection.group === group.group}
                  onClick={() => onSelectGroup(group.group)}
                >
                  <i aria-hidden="true" />
                  {group.group}
                </button>
              </li>
            ))}
          </ul>
          <div className={`series-insight-content${hasMore ? " has-more" : ""}`}>
            <div className="series-insight-items" ref={itemsRef}>
              <ol className="genre-mix-list">
                {tagged.map((item) => {
                  const tagCount = contributorTagCount(item, selection);
                  const activeGroup = contributorActiveGroup(item, selection);
                  return (
                    <li
                      key={item.contributor.id}
                      className={`${selection && tagCount === 0 ? "is-muted" : ""}`}
                    >
                      <button
                        className="genre-mix-contributor"
                        type="button"
                        aria-pressed={
                          selection?.kind === "contributor" &&
                          selection.contributorId === item.contributor.id
                        }
                        onClick={() => onSelectContributor(item.contributor.id)}
                        aria-label={item.contributor.displayName}
                        title={item.contributor.displayName}
                      >
                        {truncateContributorName(item.contributor.displayName)}
                      </button>
                      <div className="genre-mix-bar" aria-hidden="true">
                        {item.groups.map((group) => (
                          <i
                            key={group.group}
                            className={`${genreGroupClass(group.group)}${selection && activeGroup !== group.group ? " is-muted" : ""}`}
                            style={
                              {
                                "--share": `${(group.count / item.total) * 100}%`,
                              } as CSSProperties
                            }
                          />
                        ))}
                      </div>
                      <small>{tagCount}</small>
                      <span className="sr-only">
                        {item.groups.map((group) => `${group.group} ${group.count}`).join(", ")}
                      </span>
                    </li>
                  );
                })}
              </ol>
            </div>
          </div>
        </>
      )}
    </section>
  );
}

function SeriesGenreSplit({
  groups,
  selection,
  onSelectGroup,
}: {
  groups: GenreGroup[];
  selection: ActiveSelection;
  onSelectGroup: (group: string) => void;
}) {
  const total = groups.reduce((sum, group) => sum + group.count, 0);
  return (
    <section className="panel series-genre-split" aria-label="Genre split across this series">
      <span className="series-genre-split-heading">
        <strong>Genre split</strong>
        <InfoHint label="How the genre split works">
          Each color represents a genre family across tagged submissions. Select a section to focus
          that family in the details below.
        </InfoHint>
      </span>
      <GenreGroupBar
        groups={groups}
        label="Share of tagged picks by genre family"
        className="series-genre-split-bar"
        selectedGroup={selection?.kind === "group" ? selection.group : null}
        onSelectGroup={onSelectGroup}
      />
      <span className="series-genre-split-count">
        <strong>{total}</strong>
        <small>tag signals</small>
      </span>
    </section>
  );
}

/** Ignore a filter that disappeared after a background history refresh. */
function currentSelection(selection: ActiveSelection, stats: SeriesStats): ActiveSelection {
  if (selection?.kind === "contributor") {
    return stats.contributors.some((contributor) => contributor.id === selection.contributorId)
      ? selection
      : null;
  }
  if (selection?.kind === "group") {
    return stats.genreSpread.some((genre) => genre.group === selection.group) ? selection : null;
  }
  if (selection?.kind === "genre") {
    return stats.genreSpread.some((genre) => genre.name === selection.genreName) ? selection : null;
  }
  return null;
}

function genreMatchesSelection(
  genre: Genre,
  selection: ActiveSelection,
  selectedContributor: Contributor | undefined,
) {
  if (selection?.kind === "contributor")
    return selectedContributor?.genres.some((item) => item.name === genre.name) ?? false;
  if (selection?.kind === "group") return selection.group === genre.group;
  if (selection?.kind === "genre") return selection.genreName === genre.name;
  return false;
}

function contributorTagCount(item: ContributorMix, selection: ActiveSelection) {
  if (selection?.kind === "group")
    return item.groups.find((group) => group.group === selection.group)?.count ?? 0;
  if (selection?.kind === "genre")
    return item.contributor.genres.find((genre) => genre.name === selection.genreName)?.count ?? 0;
  return item.total;
}

function contributorActiveGroup(item: ContributorMix, selection: ActiveSelection) {
  if (selection?.kind === "group") return selection.group;
  if (selection?.kind === "genre")
    return (
      item.contributor.genres.find((genre) => genre.name === selection.genreName)?.group ?? null
    );
  return null;
}

function mixHeading(selection: ActiveSelection, selectedContributor: Contributor | undefined) {
  if (selectedContributor)
    return `${selectedContributor.displayName} · ${selectedContributor.genres.length} unique tags`;
  if (selection?.kind === "genre") return `Who brings ${selection.genreName}`;
  if (selection?.kind === "group") return `Who brings ${selection.group}`;
  return "Click a name or genre to explore the group.";
}

function resetScrollPosition(ref: RefObject<HTMLDivElement | null>) {
  if (ref.current) ref.current.scrollTop = 0;
}

function resetScrollPositions(...refs: RefObject<HTMLDivElement | null>[]) {
  refs.forEach(resetScrollPosition);
}

function truncateContributorName(name: string) {
  return name.length > 18 ? `${name.slice(0, 17)}…` : name;
}
