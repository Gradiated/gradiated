import { getEventListeners } from "node:events";

import { afterEach, describe, expect, it, vi } from "vitest";

import { sleep } from "../src/sleep.js";

afterEach(() => {
  vi.useRealTimers();
});

describe("sleep", () => {
  it("resolves after the delay and leaves no abort listener behind", async () => {
    vi.useFakeTimers();
    const controller = new AbortController();
    let resolved = false;

    const sleeping = sleep(1_000, controller.signal).then(() => {
      resolved = true;
    });
    await vi.advanceTimersByTimeAsync(999);

    expect(resolved).toBe(false);

    await vi.advanceTimersByTimeAsync(1);
    await sleeping;

    expect(resolved).toBe(true);
    expect(getEventListeners(controller.signal, "abort")).toHaveLength(0);
  });

  it("resolves at once when aborted", async () => {
    vi.useFakeTimers();
    const controller = new AbortController();

    const sleeping = sleep(60_000, controller.signal);
    controller.abort();
    await sleeping;

    expect(vi.getTimerCount()).toBe(0);
  });

  it("does not wait when the signal is already aborted", async () => {
    vi.useFakeTimers();

    await sleep(60_000, AbortSignal.abort());

    expect(vi.getTimerCount()).toBe(0);
  });
});
