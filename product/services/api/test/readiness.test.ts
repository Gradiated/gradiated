import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiMetrics } from "../src/metrics.js";
import {
  createReadinessCheck,
  DependencyTimeoutError,
} from "../src/readiness.js";
import { captureServiceLogs } from "./support.js";

const up = async () => "PONG";
const never = () => new Promise<never>(() => undefined);

const refused = Object.assign(new Error("connect ECONNREFUSED"), {
  code: "ECONNREFUSED",
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("readiness check", () => {
  it("reports every dependency up", async () => {
    const check = createReadinessCheck({
      pool: { query: up },
      valkey: { ping: up },
      timeoutMs: 1_000,
    });

    await expect(check()).resolves.toEqual({
      postgres: { status: "up" },
      valkey: { status: "up" },
    });
  });

  it("reports a rejected check as down and logs its error code", async () => {
    const logs = captureServiceLogs();
    const check = createReadinessCheck({
      pool: {
        query: async () => {
          throw refused;
        },
      },
      valkey: { ping: up },
      timeoutMs: 1_000,
    });

    const checks = await check();
    new ApiMetrics({ collectProcessMetrics: false }).recordDependencies(checks);

    expect(checks).toEqual({
      postgres: { status: "down", error: refused },
      valkey: { status: "up" },
    });
    expect(logs.events()).toEqual([
      expect.objectContaining({
        event: "dependency_down",
        dependency: "postgres",
        error_type: "Error",
        error_code: "ECONNREFUSED",
      }),
    ]);
  });

  it("reports a hung check as a timeout once the deadline passes", async () => {
    const logs = captureServiceLogs();
    vi.useFakeTimers();
    const check = createReadinessCheck({
      pool: { query: up },
      valkey: { ping: never },
      timeoutMs: 1_000,
    });

    const result = check();
    await vi.advanceTimersByTimeAsync(1_000);
    const checks = await result;
    new ApiMetrics({ collectProcessMetrics: false }).recordDependencies(checks);

    expect(checks).toEqual({
      postgres: { status: "up" },
      valkey: { status: "down", error: expect.any(DependencyTimeoutError) },
    });
    expect(logs.events()).toEqual([
      expect.objectContaining({
        event: "dependency_down",
        dependency: "valkey",
        error_type: "DependencyTimeoutError",
      }),
    ]);
  });
});
