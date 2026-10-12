import { getEventListeners } from "node:events";
import { afterEach, describe, expect, it, vi } from "vitest";

import { createProbeDeadline } from "../src/probe-deadline.js";

afterEach(() => vi.useRealTimers());

describe("probe deadline", () => {
  it("releases the timer and parent listener after successful passes", () => {
    vi.useFakeTimers();
    const parent = new AbortController();

    for (let pass = 0; pass < 1_000; pass++) {
      const deadline = createProbeDeadline(parent.signal, 4_000);
      expect(getEventListeners(parent.signal, "abort")).toHaveLength(1);
      deadline.dispose();
      deadline.dispose();
      expect(deadline.signal.aborted).toBe(false);
    }

    expect(getEventListeners(parent.signal, "abort")).toHaveLength(0);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("enforces the deadline and cleans up after timeout", async () => {
    vi.useFakeTimers();
    const parent = new AbortController();
    const deadline = createProbeDeadline(parent.signal, 4_000);

    await vi.advanceTimersByTimeAsync(3_999);
    expect(deadline.signal.aborted).toBe(false);
    await vi.advanceTimersByTimeAsync(1);

    expect(deadline.signal.reason).toMatchObject({ name: "TimeoutError" });
    expect(getEventListeners(parent.signal, "abort")).toHaveLength(0);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("preserves shutdown cancellation and clears its timer", () => {
    vi.useFakeTimers();
    const parent = new AbortController();
    const deadline = createProbeDeadline(parent.signal, 4_000);
    const reason = new Error("shutdown");

    parent.abort(reason);

    expect(deadline.signal.reason).toBe(reason);
    expect(getEventListeners(parent.signal, "abort")).toHaveLength(0);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("does not allocate a timer or listener after shutdown", () => {
    vi.useFakeTimers();
    const parent = AbortSignal.abort(new Error("already stopped"));
    const deadline = createProbeDeadline(parent, 4_000);

    expect(deadline.signal.reason).toBe(parent.reason);
    expect(getEventListeners(parent, "abort")).toHaveLength(0);
    expect(vi.getTimerCount()).toBe(0);
  });
});
