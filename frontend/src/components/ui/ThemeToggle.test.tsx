import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";

import { ThemeToggle } from "./ThemeToggle";

afterEach(() => {
  cleanup();
  document.documentElement.removeAttribute("data-theme");
  window.localStorage.removeItem("music-rounds-theme");
});

describe("ThemeToggle", () => {
  it("persists the selected dark theme and offers a light-theme return action", async () => {
    const user = userEvent.setup();
    render(<ThemeToggle />);

    await user.click(screen.getByRole("button", { name: "Use dark theme" }));

    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(window.localStorage.getItem("music-rounds-theme")).toBe("dark");
    expect(screen.getByRole("button", { name: "Use light theme" })).toBeTruthy();
  });
});
