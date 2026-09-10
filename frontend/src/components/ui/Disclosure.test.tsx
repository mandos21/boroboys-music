import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { Disclosure } from "./Disclosure";

describe("Disclosure", () => {
  it("uses the shared Base UI collapsible behavior", async () => {
    const user = userEvent.setup();
    render(
      <Disclosure description="Optional details" title="Advanced options">
        <p>Hidden until requested.</p>
      </Disclosure>,
    );

    expect(screen.queryByText("Hidden until requested.")).toBeNull();
    await user.click(screen.getByRole("button", { name: /advanced options/i }));
    expect(await screen.findByText("Hidden until requested.")).toBeTruthy();
  });
});
