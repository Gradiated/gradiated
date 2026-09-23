import { describe, expect, it } from "vitest";

import type { TrainingRunRow } from "@/store/fine-tuning-types";
import {
  currentVersion,
  traceSummaries,
  versionsForTask,
} from "@/store/fine-tuning-views";

import { seededSupportTriage, traceRow } from "./support/fine-tuning";

const {
  seed,
  task: supportTriage,
  version: seededVersion,
} = seededSupportTriage();

describe("versionsForTask", () => {
  it("skips a model whose run has no evaluation", () => {
    const training_runs = seed.training_runs.map((run): TrainingRunRow =>
      run.id === seededVersion.run.id ? { ...run, evaluation: null } : run,
    );

    expect(
      versionsForTask({ ...seed, training_runs }, supportTriage.id).map(
        (version) => version.model.id,
      ),
    ).not.toContain(seededVersion.model.id);
  });
});

describe("currentVersion", () => {
  it("prefers the production version over a newer one", () => {
    const versions = versionsForTask(seed, supportTriage.id);

    expect(versions[0]?.is_production).toBe(false);
    expect(currentVersion(versions)?.model.id).toBe(
      supportTriage.production_model_id,
    );
  });

  it("falls back to the newest version before any promotion", () => {
    const tasks = seed.tasks.map((task) =>
      task.id === supportTriage.id
        ? { ...task, production_model_id: null }
        : task,
    );
    const versions = versionsForTask({ ...seed, tasks }, supportTriage.id);

    expect(currentVersion(versions)).toBe(versions[0]);
    expect(currentVersion([])).toBeUndefined();
  });
});

describe("traceSummaries", () => {
  it("groups generations by trace, newest trace first", () => {
    const rows = [
      traceRow({
        id: "g2",
        trace_id: "t1",
        captured_at: "2026-09-01T00:00:02.000Z",
        latency_ms: 300,
        cost_nano_usd: 5,
      }),
      traceRow({
        id: "g1",
        trace_id: "t1",
        captured_at: "2026-09-01T00:00:00.000Z",
        latency_ms: 100,
        cost_nano_usd: 7,
      }),
      traceRow({
        id: "g3",
        trace_id: "g3",
        captured_at: "2026-09-02T00:00:00.000Z",
      }),
      traceRow({
        id: "g4",
        trace_id: "t9",
        task: "email-draft",
        captured_at: "2026-09-03T00:00:00.000Z",
      }),
    ];

    expect(traceSummaries(rows, "support-triage")).toEqual([
      {
        trace_id: "g3",
        started_at: "2026-09-02T00:00:00.000Z",
        generation_count: 1,
        duration_ms: 100,
        cost_nano_usd: 1_000,
        single_generation: true,
      },
      {
        trace_id: "t1",
        started_at: "2026-09-01T00:00:00.000Z",
        generation_count: 2,
        duration_ms: 2_300,
        cost_nano_usd: 12,
        single_generation: false,
      },
    ]);
  });
});
