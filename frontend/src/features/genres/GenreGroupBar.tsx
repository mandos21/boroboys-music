import type { CSSProperties } from "react";

import type { GenreGroup } from "./genre";
import { genreGroupClass } from "./genre";

export function GenreGroupBar({
  groups,
  label,
  className,
  selectedGroup,
  onSelectGroup,
}: {
  groups: readonly GenreGroup[];
  label: string;
  className?: string;
  selectedGroup?: string | null;
  onSelectGroup?: (group: string) => void;
}) {
  const total = groups.reduce((sum, group) => sum + group.count, 0);
  const accessibleLabel = `${label}: ${groups.map((group) => `${group.group} ${group.count}`).join(", ")}`;
  const sharedProps = (group: GenreGroup) => ({
    className: genreGroupClass(group.group),
    style: { "--share": `${(group.count / total) * 100}%` } as CSSProperties,
  });

  return (
    <div
      className={`genre-group-bar${className ? ` ${className}` : ""}`}
      {...(!onSelectGroup ? { role: "img", "aria-label": accessibleLabel } : {})}
    >
      {groups.map((group) =>
        onSelectGroup ? (
          <button
            {...sharedProps(group)}
            key={group.group}
            type="button"
            aria-pressed={selectedGroup === group.group}
            aria-label={`${group.group}: ${group.count} tags`}
            title={`${group.group}: ${group.count} tags`}
            onClick={() => onSelectGroup(group.group)}
          >
            <i aria-hidden="true" />
          </button>
        ) : (
          <i {...sharedProps(group)} key={group.group} aria-hidden="true" />
        ),
      )}
    </div>
  );
}
