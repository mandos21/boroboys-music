import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const notify = vi.hoisted(() => ({
  error: vi.fn(),
  info: vi.fn(),
  success: vi.fn(),
}));

vi.mock("sonner", () => ({
  Toaster: () => null,
  toast: notify,
}));

import { ToastProvider, useToast } from "./ToastProvider";

function Publisher() {
  const { showToast } = useToast();
  return (
    <>
      <button
        type="button"
        onClick={() => showToast({ title: "Saved", description: "Your note is ready." })}
      >
        success
      </button>
      <button type="button" onClick={() => showToast({ title: "Couldn’t save", tone: "error" })}>
        error
      </button>
    </>
  );
}

describe("ToastProvider", () => {
  it("keeps feature notifications on the shared Sonner delivery contract", () => {
    render(
      <ToastProvider>
        <Publisher />
      </ToastProvider>,
    );

    screen.getByRole("button", { name: "success" }).click();
    screen.getByRole("button", { name: "error" }).click();

    expect(notify.success).toHaveBeenCalledWith("Saved", {
      description: "Your note is ready.",
      duration: 5_000,
    });
    expect(notify.error).toHaveBeenCalledWith("Couldn’t save", {
      description: undefined,
      duration: 5_000,
    });
  });
});
