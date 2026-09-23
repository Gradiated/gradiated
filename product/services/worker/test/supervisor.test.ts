import { access, mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { supervise, type LoopHealth } from "../src/supervisor.js";

let directory: string;
let readinessPath: string;

beforeEach(async () => {
  vi.spyOn(console, "log").mockImplementation(() => undefined);
  directory = await mkdtemp(path.join(tmpdir(), "worker-supervisor-"));
  readinessPath = path.join(directory, "ready");
});

afterEach(async () => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  await rm(directory, { recursive: true, force: true });
});

const loopHealth = (): LoopHealth => ({
  loopStarted: vi.fn(),
  loopReadyNow: vi.fn(),
  loopFailed: vi.fn(),
  loopStopped: vi.fn(),
});

const isReady = async (): Promise<boolean> =>
  access(readinessPath).then(
    () => true,
    () => false,
  );

describe("loop supervisor", () => {
  it("doubles the retry delay to a 30 second cap and resets it after a healthy run", async () => {
    vi.useFakeTimers({
      now: 0,
      toFake: ["setTimeout", "clearTimeout", "Date"],
    });
    const controller = new AbortController();
    const outcomes = [
      ...Array.from({ length: 7 }, () => "fail"),
      "healthy",
      "fail",
    ];
    const startedAt: number[] = [];
    const run = vi.fn(async () => {
      startedAt.push(Date.now());
      const outcome = outcomes.shift();

      if (outcome === undefined) {
        controller.abort();
        return;
      }

      if (outcome === "healthy") {
        await new Promise((resolve) => setTimeout(resolve, 60_000));
      }

      throw new Error("loop failed");
    });

    const supervising = supervise({
      loop: "settlement",
      readinessPath,
      metrics: loopHealth(),
      signal: controller.signal,
      run,
    });
    let settled = false;
    void supervising.finally(() => {
      settled = true;
    });
    while (!settled) {
      await vi.runOnlyPendingTimersAsync();
      await new Promise((resolve) => setImmediate(resolve));
    }

    const delays = startedAt.slice(1).map((time, index) => {
      const previous = startedAt[index] ?? 0;

      return time - previous;
    });
    expect(delays).toEqual([
      1_000, 2_000, 4_000, 8_000, 16_000, 30_000, 30_000, 61_000, 2_000,
    ]);
  });

  it("marks the loop ready and removes the readiness file when the loop fails", async () => {
    const controller = new AbortController();
    const metrics = loopHealth();
    let readyBeforeFailure = false;

    await supervise({
      loop: "generation_ingestion",
      readinessPath,
      metrics,
      signal: controller.signal,
      run: async (markReady) => {
        await markReady();
        readyBeforeFailure = await isReady();
        controller.abort();
        throw new Error("loop failed");
      },
    });

    expect(readyBeforeFailure).toBe(true);
    expect(metrics.loopReadyNow).toHaveBeenCalledWith("generation_ingestion");
    expect(await isReady()).toBe(false);
  });

  it("reports start, restart, failure and stop to the loop metrics", async () => {
    const controller = new AbortController();
    const metrics = loopHealth();
    let attempts = 0;

    await supervise({
      loop: "settlement",
      readinessPath,
      metrics,
      signal: controller.signal,
      run: async () => {
        attempts += 1;
        if (attempts === 1) throw new Error("loop failed");

        controller.abort();
      },
    });

    expect(vi.mocked(metrics.loopStarted).mock.calls).toEqual([
      ["settlement", false],
      ["settlement", true],
    ]);
    expect(metrics.loopFailed).toHaveBeenCalledOnce();
    expect(metrics.loopStopped).toHaveBeenCalledWith("settlement");
  });

  it("ends during the retry delay when aborted", async () => {
    const controller = new AbortController();
    const run = vi.fn(async () => {
      setTimeout(() => controller.abort(), 10);
      throw new Error("loop failed");
    });

    await supervise({
      loop: "settlement",
      readinessPath,
      metrics: loopHealth(),
      signal: controller.signal,
      run,
    });

    expect(run).toHaveBeenCalledOnce();
  });
});
