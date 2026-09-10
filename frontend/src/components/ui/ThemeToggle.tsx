import { useEffect, useState } from "react";
import { Moon, Sun } from "lucide-react";

import { Button } from "./button";

type Theme = "light" | "dark";

function initialTheme(): Theme {
  if (typeof window === "undefined") return "light";
  const saved = window.localStorage.getItem("music-rounds-theme");
  if (saved === "light" || saved === "dark") return saved;
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(initialTheme);
  const isDark = theme === "dark";

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    window.localStorage.setItem("music-rounds-theme", theme);
  }, [theme]);

  return (
    <Button
      aria-label={isDark ? "Use light theme" : "Use dark theme"}
      className="icon-button theme-toggle"
      onClick={() => setTheme(isDark ? "light" : "dark")}
      size="icon"
      title={isDark ? "Use light theme" : "Use dark theme"}
      type="button"
      variant="ghost"
    >
      {isDark ? <Sun aria-hidden="true" size={18} /> : <Moon aria-hidden="true" size={18} />}
    </Button>
  );
}
