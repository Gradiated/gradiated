import { describe, expect, it } from "vitest";

import {
  describeEvent,
  runLogByStage,
  runProgress,
  runTimeline,
} from "@/store/fine-tuning-run-log";
import type { TrainingRunEventPayload } from "@/store/fine-tuning-types";

import { runEvent } from "./support/fine-tuning";

type PayloadByType = {
  [Type in TrainingRunEventPayload["type"]]: Extract<
    TrainingRunEventPayload,
    { type: Type }
  >;
};

const gpu = { type: "NVIDIA H200", count: 8 };
const digest = "a".repeat(64);

const progress = (step: number): PayloadByType["trainer_progress"] => ({
  type: "trainer_progress",
  step,
  total_steps: 100,
  train_loss: 0.5,
  metrics: { learning_rate: 0.0002 },
  tokens_per_second: 1_000,
  eta_seconds: 60,
});

const everyPayload = {
  run_created: {
    type: "run_created",
    trigger: "manual",
    requested_by: "member@example.com",
    task_id: "task",
    base_model_id: "base",
  },
  stage_entered: { type: "stage_entered", stage: "training" },
  dataset_built: {
    type: "dataset_built",
    eligible_examples: 10,
    duplicates_removed: 9,
    train: 7,
    validation: 1,
    test: 1,
    oldest_trace_at: "2026-08-01T00:00:00.000Z",
    newest_trace_at: "2026-09-01T00:00:00.000Z",
  },
  capacity_granted: { type: "capacity_granted", host_id: "host-1", gpu },
  job_submitted: {
    type: "job_submitted",
    runner: "nomad",
    provider_job_id: "job-1",
    host_id: "host-1",
    gpu,
  },
  job_status: { type: "job_status", state: "running", message: "ok" },
  model_reserved: { type: "model_reserved", model_id: "model-1" },
  artifact_verified: {
    type: "artifact_verified",
    model_id: "model-1",
    sha256: digest,
    size_bytes: 1_048_576,
  },
  adapter_loaded: { type: "adapter_loaded", host_id: "host-1" },
  evaluation_progress: { type: "evaluation_progress", completed: 1, total: 2 },
  evaluation_completed: {
    type: "evaluation_completed",
    judge: "openai/gpt-5",
    groups: 3,
    win: 0.5,
    tie: 0.2,
    loss: 0.2,
    unresolved: 0.1,
  },
  published: { type: "published", model_id: "model-1" },
  cancel_requested: { type: "cancel_requested", requested_by: "member" },
  run_finished: {
    type: "run_finished",
    stage: "failed",
    error_code: "attempt_deadline",
    message: "deadline reached",
  },
  note: { type: "note", level: "warning", message: "slow host" },
  trainer_progress: progress(10),
  trainer_observation: {
    type: "trainer_observation",
    name: "validation_completed",
    message: "Validation completed",
    step: 10,
    metrics: { validation_loss: 0.6, accuracy: 0.7 },
  },
  trainer_checkpoint: {
    type: "trainer_checkpoint",
    step: 10,
    key: "runs/example/checkpoint.tar.gz",
    sha256: digest,
    size_bytes: 1024,
  },
} satisfies PayloadByType;

describe("runLogByStage", () => {
  it("groups control-plane events under the latest stage entered", () => {
    const created = runEvent(1, "worker", everyPayload.run_created);
    const queued = runEvent(2, "worker", {
      type: "stage_entered",
      stage: "queued",
    });
    const building = runEvent(3, "worker", {
      type: "stage_entered",
      stage: "building_dataset",
    });
    const built = runEvent(4, "worker", everyPayload.dataset_built);

    expect(runLogByStage([created, queued, building, built])).toEqual({
      queued: [created, queued],
      building_dataset: [building, built],
    });
  });

  it("keeps trainer events in training after a later stage is entered", () => {
    const training = runEvent(1, "worker", {
      type: "stage_entered",
      stage: "training",
    });
    const verifying = runEvent(2, "worker", {
      type: "stage_entered",
      stage: "verifying",
    });
    const lateProgress = runEvent(3, "trainer", progress(100));
    const finished = runEvent(4, "trainer", everyPayload.trainer_observation);

    expect(
      runLogByStage([training, verifying, lateProgress, finished]),
    ).toEqual({
      training: [training, lateProgress, finished],
      verifying: [verifying],
    });
  });
});

describe("describeEvent", () => {
  it.each(Object.values(everyPayload))("describes $type", (payload) => {
    expect(describeEvent(runEvent(1, "worker", payload))).not.toBe("");
  });
});

describe("runProgress", () => {
  it("returns null before the trainer reports progress", () => {
    expect(
      runProgress([runEvent(1, "worker", everyPayload.run_created)]),
    ).toBeNull();
  });

  it("returns the latest trainer progress", () => {
    const events = [
      runEvent(1, "trainer", progress(10)),
      runEvent(2, "trainer", progress(40)),
      runEvent(3, "trainer", everyPayload.trainer_checkpoint),
    ];

    expect(runProgress(events)).toEqual({
      step: 40,
      total_steps: 100,
      train_loss: 0.5,
      metrics: { learning_rate: 0.0002 },
      tokens_per_second: 1_000,
      eta_seconds: 60,
    });
  });
});

it("renders sparse progress and retains extra numeric metrics", () => {
  const event = runEvent(1, "trainer", {
    type: "trainer_progress",
    step: 2,
    metrics: { "custom/reward": 0.4 },
  });
  expect(describeEvent(event)).toBe("step 2 custom/reward=0.4");
  expect(runProgress([event])?.metrics).toEqual({ "custom/reward": 0.4 });
});

it("keeps validation attached to its training step without replacing progress", () => {
  const events = [
    runEvent(1, "trainer", progress(10)),
    runEvent(2, "worker", { type: "stage_entered", stage: "publishing" }),
    runEvent(3, "trainer", {
      type: "trainer_observation",
      name: "validation_completed",
      message: "Validation completed",
      step: 10,
      metrics: { validation_loss: 0.7, accuracy: 0.8 },
    }),
  ];
  expect(runProgress(events)?.step).toBe(10);
  expect(runLogByStage(events).training).toContain(events[2]);
  expect(describeEvent(events[2]!)).toBe(
    "Validation completed (step 10) validation_loss=0.7 accuracy=0.8",
  );
});

it("renders an unfamiliar observation without treating it as a transition", () => {
  const event = runEvent(1, "trainer", {
    type: "trainer_observation",
    name: "stage_entered",
    message: "An internal trainer observation",
    details: { stage: "succeeded", flags: ["custom"] },
  });
  expect(runTimeline([event])).toEqual([]);
  expect(runProgress([event])).toBeNull();
  expect(describeEvent(event)).toContain('"flags":["custom"]');
  expect(runLogByStage([event]).training).toEqual([event]);
});
