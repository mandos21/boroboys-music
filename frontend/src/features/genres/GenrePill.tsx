import type { Genre } from "./genre";
import { genreGroupClass } from "./genre";

export function GenrePill({
  genre,
  highlighted = false,
  muted = false,
  onSelect,
  selected = false,
}: {
  genre: Genre;
  highlighted?: boolean;
  muted?: boolean;
  onSelect?: () => void;
  selected?: boolean;
}) {
  const className = `genre-token ${genreGroupClass(genre.group)}${highlighted ? " is-highlighted" : ""}${muted ? " is-muted" : ""}`;
  const content = (
    <>
      <i aria-hidden="true" />
      {genre.name} <small>{genre.count}</small>
    </>
  );

  if (onSelect) {
    return (
      <button className={className} type="button" aria-pressed={selected} onClick={onSelect}>
        {content}
      </button>
    );
  }
  return <span className={className}>{content}</span>;
}
