import { describe, expect, it } from "vitest";

import {
  downsample,
  evalMetricNames,
  evalSeries,
  isRunFinished,
  lastEventSeq,
  lossSeries,
  mergeRunEvents,
  phaseStepIndex,
  runTimeline,
} from "@/lib/grad/run-events";
import type { RunEvent } from "@/lib/grad/types";

const runId = "run_1";
const at = (minute: number) =>
  `2026-11-27T12:${String(minute).padStart(2, "0")}:00Z`;

const phase = (
  seq: number,
  attempt: number,
  name: Extract<RunEvent, { type: "phase" }>["phase"],
  gpu = false,
): RunEvent => ({
  type: "phase",
  runId,
  seq,
  attempt,
  timestamp: at(seq),
  phase: name,
  step: 0,
  workersOnline: null,
  autoscaling: null,
  gpu: gpu ? { name: "NVIDIA H100 80GB", memoryGb: 80 } : null,
});

const metric = (
  seq: number,
  attempt: number,
  step: number,
  loss: number,
  evalLoss?: number,
): RunEvent => ({
  type: "metric",
  runId,
  seq,
  attempt,
  timestamp: at(seq),
  step,
  metric: {
    seq,
    attempt,
    step,
    loss,
    ...(evalLoss === undefined
      ? {}
      : {
          evalLoss,
          evalMetrics: { eval_loss: evalLoss, eval_token_accuracy: null },
        }),
    tokens: step * 10,
    costUsd: step / 100,
    timestamp: at(seq),
  },
});

const attempt = (
  seq: number,
  number: number,
  event: "started" | "interrupted" | "gave_up",
  extra: Partial<Extract<RunEvent, { type: "attempt" }>> = {},
): RunEvent => ({
  type: "attempt",
  runId,
  seq,
  attempt: number,
  timestamp: at(seq),
  event,
  reason: null,
  step: null,
  resumeStep: null,
  maxAttempts: 3,
  message: "spot instance preempted",
  ...extra,
});

const completed = (seq: number): RunEvent => ({
  type: "completed",
  runId,
  seq,
  attempt: 2,
  timestamp: at(seq),
  status: "completed",
  run: {} as Extract<RunEvent, { type: "completed" }>["run"],
});

describe("mergeRunEvents", () => {
  it("orders by seq, drops repeats and keeps completed last", () => {
    const merged = mergeRunEvents(
      [phase(1, 1, "queued"), metric(3, 1, 20, 1.2)],
      [completed(3), phase(2, 1, "starting"), metric(3, 1, 20, 1.2)],
    );

    expect(merged.map((event) => `${event.type}:${event.seq}`)).toEqual([
      "phase:1",
      "phase:2",
      "metric:3",
      "completed:3",
    ]);
    expect(isRunFinished(merged)).toBe(true);
    expect(lastEventSeq(merged)).toBe(3);
  });

  it("drops the completed event once a resumed run continues", () => {
    const merged = mergeRunEvents(
      [phase(1, 1, "training"), completed(1)],
      [attempt(2, 2, "started", { resumeStep: 800 })],
    );

    expect(merged.map((event) => event.type)).toEqual(["phase", "attempt"]);
    expect(isRunFinished(merged)).toBe(false);
  });

  it("starts from zero without events", () => {
    expect(lastEventSeq([])).toBe(0);
    expect(isRunFinished([])).toBe(false);
  });
});

describe("lossSeries", () => {
  it("lets a resumed attempt replace the steps it repeats", () => {
    const series = lossSeries([
      metric(1, 1, 20, 1.5),
      metric(2, 1, 40, 1.3, 1.4),
      metric(3, 1, 60, 1.2),
      metric(4, 2, 40, 1.25),
      metric(5, 2, 60, 1.1),
    ]);

    expect(series).toEqual([
      { step: 20, loss: 1.5 },
      { step: 40, loss: 1.25 },
      { step: 60, loss: 1.1 },
    ]);
  });

  it("keeps eval points and the last point when it thins a long run", () => {
    const events = Array.from({ length: 1000 }, (_, index) =>
      metric(
        index + 1,
        1,
        (index + 1) * 2,
        1,
        (index + 1) % 333 === 0 ? 0.9 : undefined,
      ),
    );

    const series = lossSeries(events, 100);

    expect(series.length).toBeLessThanOrEqual(104);
    expect(series.at(-1)?.step).toBe(2000);
    expect(series.filter((point) => point.evalLoss !== undefined)).toHaveLength(
      3,
    );
  });

  it("keeps short series as they are", () => {
    const points = [{ step: 1 }, { step: 2 }];

    expect(downsample(points, () => false, 10)).toEqual(points);
  });
});

describe("evalSeries", () => {
  it("collects numeric held-out metrics by step", () => {
    const points = evalSeries([
      metric(1, 1, 20, 1.2),
      metric(2, 1, 40, 1.1, 1.3),
    ]);

    expect(points).toEqual([{ step: 40, values: { eval_loss: 1.3 } }]);
    expect(evalMetricNames(points)).toEqual(["eval_loss"]);
  });
});

describe("runTimeline", () => {
  const events = [
    phase(1, 1, "queued"),
    attempt(2, 1, "started"),
    phase(3, 1, "starting", true),
    phase(4, 1, "training"),
    phase(5, 1, "evaluating"),
    phase(6, 1, "training"),
    attempt(7, 1, "interrupted", {
      reason: "compute_reclaimed",
      step: 860,
      resumeStep: 800,
    }),
    attempt(8, 2, "started", { resumeStep: 800 }),
    phase(9, 2, "training"),
    completed(9),
  ];

  it("lists phase changes and attempts without repeating training phases", () => {
    expect(runTimeline(events).map((entry) => entry.title)).toEqual([
      "Queued",
      "Attempt 1 started",
      "Starting",
      "Training",
      "Compute reclaimed at step 860",
      "Attempt 2 started",
      "Training",
      "Run completed",
    ]);
  });

  it("describes where each attempt resumes", () => {
    const entries = runTimeline(events);

    expect(entries.find((entry) => entry.title === "Starting")?.detail).toBe(
      "NVIDIA H100 80GB · 80 GB",
    );
    expect(entries[4]?.detail).toBe("The next attempt resumes from step 800.");
    expect(entries[5]?.detail).toBe("Resumed from the checkpoint at step 800");
  });

  it("uses neutral wording, not the worker's own message", () => {
    const text = JSON.stringify(runTimeline(events)).toLowerCase();

    expect(text).not.toContain("spot");
    expect(text).not.toContain("preempt");
  });

  it("reports a run that ran out of attempts", () => {
    const entries = runTimeline([attempt(1, 3, "gave_up")]);

    expect(entries).toEqual([
      expect.objectContaining({
        title: "No attempts left",
        tone: "danger",
        detail: "Stopped after 3 attempts without a result.",
      }),
    ]);
  });
});

describe("phaseStepIndex", () => {
  it("maps phases to the progress steps", () => {
    expect(phaseStepIndex(null)).toBe(0);
    expect(phaseStepIndex("waiting_for_compute")).toBe(0);
    expect(phaseStepIndex("loading_model")).toBe(1);
    expect(phaseStepIndex("checkpointing")).toBe(2);
    expect(phaseStepIndex("completing")).toBe(3);
  });
});
