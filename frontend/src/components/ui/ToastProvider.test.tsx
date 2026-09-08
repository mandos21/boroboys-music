import { act, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ToastProvider, useToast } from "./ToastProvider";

afterEach(() => vi.useRealTimers());

function Publisher() {
  const { showToast } = useToast();
  return (
    <>
      <button type="button" onClick={() => showToast({ title: "First" })}>first</button>
      <button type="button" onClick={() => showToast({ title: "Second" })}>second</button>
    </>
  );
}

describe("ToastProvider", () => {
  it("keeps each notification on its own countdown", () => {
    vi.useFakeTimers();
    render(
      <ToastProvider>
        <Publisher />
      </ToastProvider>,
    );

    act(() => screen.getByRole("button", { name: "first" }).click());
    expect(screen.getByText("First")).toBeTruthy();

    // A later notification must not restart the earlier one's five seconds.
    act(() => void vi.advanceTimersByTime(4_000));
    act(() => screen.getByRole("button", { name: "second" }).click());
    act(() => void vi.advanceTimersByTime(1_500));

    expect(screen.queryByText("First")).toBeNull();
    expect(screen.getByText("Second")).toBeTruthy();
  });
});
