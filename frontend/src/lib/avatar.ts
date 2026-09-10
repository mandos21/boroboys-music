import type { CSSProperties } from "react";

const palette = [
  ["#dcfce7", "#166534", "#1b3825", "#86efac"],
  ["#ccfbf1", "#0f766e", "#163b38", "#5eead4"],
  ["#dbeafe", "#1d4ed8", "#172e4e", "#93c5fd"],
  ["#f3e8ff", "#7e22ce", "#31254b", "#d8b4fe"],
  ["#ffedd5", "#9a3412", "#442617", "#fdba74"],
];

export function avatarStyle(name: string | null): CSSProperties {
  const hash = [...(name ?? "?")].reduce(
    (value, character) => (value * 31 + character.charCodeAt(0)) >>> 0,
    7,
  );
  const [background, color, darkBackground, darkColor] = palette[hash % palette.length];
  return {
    "--avatar-background": background,
    "--avatar-color": color,
    "--avatar-dark-background": darkBackground,
    "--avatar-dark-color": darkColor,
  } as CSSProperties;
}
