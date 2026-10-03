import { Registry } from "prom-client";
import { afterEach, describe, expect, it, vi } from "vitest";
import { TrainingMetrics } from "../src/training/metrics.js";

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("training metrics", () => {
  it("keeps the metrics endpoint responsive when the database observation stalls", async () => {
    const registry = new Registry();
    const read = vi.fn(() => new Promise<never>(() => {}));
    const metrics = new TrainingMetrics(registry, read);
    void metrics.collect();
    expect(await registry.metrics()).toContain(
      "gradiated_training_metrics_available",
    );
    expect(read).toHaveBeenCalledTimes(1);
  });

  it("coalesces scrapes, resets empty stages, and removes stale values on failures", async () => {
    vi.useFakeTimers();
    const registry = new Registry();
    const read = vi.fn().mockResolvedValue([
      { kind: "completed_recent", stage: "failed", value: 1 },
      { kind: "active", stage: "awaiting_capacity", value: 3 },
      { kind: "oldest", stage: "awaiting_capacity", value: 120 },
      { kind: "duration", stage: "awaiting_capacity", value: 50 },
    ]);
    const metrics = new TrainingMetrics(registry, read);
    await Promise.all([metrics.collect(), metrics.collect()]);
    let body = await registry.metrics();
    expect(read).toHaveBeenCalledTimes(1);
    expect(body).toContain(
      'gradiated_training_active_runs{stage="awaiting_capacity"} 3',
    );
    expect(body).toContain(
      'gradiated_training_oldest_stage_seconds{stage="awaiting_capacity"} 120',
    );
    expect(body).toContain(
      'gradiated_training_completed_runs_1h{stage="failed"} 1',
    );
    expect(body).not.toContain("workspace_id");
    expect(body).not.toContain("run_id");
    read.mockResolvedValueOnce([]);
    vi.advanceTimersByTime(30_000);
    await metrics.collect();
    body = await registry.metrics();
    expect(body).toContain(
      'gradiated_training_active_runs{stage="awaiting_capacity"} 0',
    );
    expect(body).not.toContain(
      "gradiated_training_stage_duration_p95_seconds_24h{",
    );
    expect(body).toContain(
      'gradiated_training_completed_runs_1h{stage="failed"} 0',
    );
    const warning = vi.spyOn(console, "warn").mockImplementation(() => {});
    read.mockRejectedValueOnce(new Error("private-database-credential"));
    vi.advanceTimersByTime(30_000);
    await metrics.collect();
    body = await registry.metrics();
    expect(body).toContain("gradiated_training_metrics_available 0");
    expect(body).not.toContain("gradiated_training_active_runs{");
    expect(warning).toHaveBeenCalledExactlyOnceWith(
      JSON.stringify({
        service: "temporal-worker",
        event: "training_metrics_observation_failed",
      }),
    );
    expect(JSON.stringify(warning.mock.calls)).not.toContain(
      "private-database-credential",
    );
  });
});
