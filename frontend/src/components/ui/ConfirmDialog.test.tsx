import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ConfirmDialog } from "./ConfirmDialog";

describe("ConfirmDialog", () => {
  it("keeps destructive actions behind the shared alert dialog", () => {
    const onConfirm = vi.fn();
    render(
      <ConfirmDialog
        confirmLabel="Remove member"
        description="This cannot be undone."
        onConfirm={onConfirm}
        onOpenChange={vi.fn()}
        open
        title="Remove this member?"
      />,
    );

    expect(screen.getByRole("alertdialog", { name: "Remove this member?" })).toBeTruthy();
    screen.getByRole("button", { name: "Remove member" }).click();
    expect(onConfirm).toHaveBeenCalledOnce();
  });
});
