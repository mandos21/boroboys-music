import type { CSSProperties } from "react";

const palette = [
  ["#dcfce7", "#166534"],
  ["#ccfbf1", "#0f766e"],
  ["#dbeafe", "#1d4ed8"],
  ["#f3e8ff", "#7e22ce"],
  ["#ffedd5", "#9a3412"],
];

export function avatarStyle(name: string | null): CSSProperties {
  const hash = [...(name ?? "?")].reduce(
    (value, character) => (value * 31 + character.charCodeAt(0)) >>> 0,
    7,
  );
  const [background, color] = palette[hash % palette.length];
  return { "--avatar-background": background, "--avatar-color": color } as CSSProperties;
}
