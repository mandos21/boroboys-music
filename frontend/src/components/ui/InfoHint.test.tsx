import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { InfoHint } from "./InfoHint";

describe("InfoHint", () => {
  it("opens its explanation when the question mark is clicked", async () => {
    const user = userEvent.setup();
    render(
      <InfoHint label="How listening evidence works">Recent plays can take a moment.</InfoHint>,
    );

    await user.click(screen.getByRole("button", { name: "How listening evidence works" }));
    expect(await screen.findByText("Recent plays can take a moment.")).toBeTruthy();
  });
});
