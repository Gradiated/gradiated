import { describe, expect, it } from "vitest";

import {
  describeEvent,
  runLogByStage,
  runProgress,
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
  loss: 0.5,
  mean_reward: 0.6,
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
    usable: 10,
    deduplicated: 9,
    train: 7,
    validation: 1,
    holdout: 1,
    oldest_trace_at: "2026-08-01T00:00:00.000Z",
    newest_trace_at: "2026-09-01T00:00:00.000Z",
    train_sha256: digest,
    holdout_sha256: digest,
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
  trainer_started: {
    type: "trainer_started",
    gpu,
    image_digest: digest,
    recipe: "grpo",
  },
  trainer_stage: { type: "trainer_stage", stage: "training" },
  trainer_progress: progress(10),
  trainer_checkpoint: { type: "trainer_checkpoint", step: 10, sha256: digest },
  trainer_artifact_uploaded: {
    type: "trainer_artifact_uploaded",
    name: "adapter.safetensors",
    sha256: digest,
    size_bytes: 1_048_576,
  },
  trainer_finished: { type: "trainer_finished", manifest_sha256: digest },
  trainer_failed: {
    type: "trainer_failed",
    error_code: "oom",
    message: "out of memory",
  },
} satisfies PayloadByType;

describe("runLogByStage", () => {
  it("groups control-plane events under the latest stage entered", () => {
    const created = runEvent(1, "control_plane", everyPayload.run_created);
    const queued = runEvent(2, "control_plane", {
      type: "stage_entered",
      stage: "queued",
    });
    const building = runEvent(3, "control_plane", {
      type: "stage_entered",
      stage: "building_dataset",
    });
    const built = runEvent(4, "control_plane", everyPayload.dataset_built);

    expect(runLogByStage([created, queued, building, built])).toEqual({
      queued: [created, queued],
      building_dataset: [building, built],
    });
  });

  it("keeps trainer events in training after a later stage is entered", () => {
    const training = runEvent(1, "control_plane", {
      type: "stage_entered",
      stage: "training",
    });
    const verifying = runEvent(2, "control_plane", {
      type: "stage_entered",
      stage: "verifying",
    });
    const lateProgress = runEvent(3, "trainer", progress(100));
    const finished = runEvent(4, "trainer", everyPayload.trainer_finished);

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
    expect(describeEvent(runEvent(1, "control_plane", payload))).not.toBe("");
  });
});

describe("runProgress", () => {
  it("returns null before the trainer reports progress", () => {
    expect(
      runProgress([runEvent(1, "control_plane", everyPayload.run_created)]),
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
      loss: 0.5,
      mean_reward: 0.6,
      tokens_per_second: 1_000,
      eta_seconds: 60,
    });
  });
});
