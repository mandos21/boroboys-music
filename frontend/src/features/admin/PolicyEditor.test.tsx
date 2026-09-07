import { useState } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { PolicyEditor } from "./PolicyEditor";

function PolicyEditorHarness() {
  const [policies, setPolicies] = useState<Record<string, unknown>[]>([]);
  return <PolicyEditor value={policies} onChange={setPolicies} />;
}

describe("PolicyEditor", () => {
  it("adds a supported policy with a safe default and lets an admin remove it", async () => {
    const user = userEvent.setup();
    render(<PolicyEditorHarness />);

    await user.selectOptions(screen.getByLabelText("Add a check"), "no_duplicate_in_round");

    expect(screen.getByText("No duplicate in this round")).toBeTruthy();
    expect(screen.getByLabelText("On match")).toHaveProperty("value", "reject");

    await user.click(screen.getByRole("button", { name: "Remove" }));

    expect(screen.getByText(/No round-specific checks/i)).toBeTruthy();
  });
});
