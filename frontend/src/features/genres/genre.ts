import type { components } from "../../api/schema";

export type Genre = components["schemas"]["ProfileGenreItemResponse"];
export type GenreGroup = { group: string; count: number };

export function genreGroupClass(group: string) {
  return `genre-token-${group.replaceAll(" ", "-")}`;
}

export function genreGroupTotals(genres: readonly Genre[]): GenreGroup[] {
  const totals = new Map<string, number>();
  genres.forEach((genre) => totals.set(genre.group, (totals.get(genre.group) ?? 0) + genre.count));
  return [...totals.entries()]
    .map(([group, count]) => ({ group, count }))
    .sort((left, right) => right.count - left.count || left.group.localeCompare(right.group));
}
