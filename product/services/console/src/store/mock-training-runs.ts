import { runProgress } from "@/store/fine-tuning-run-log";
import {
  isTerminalStage,
  type AdapterArtifact,
  type EvaluationJudge,
  type EvaluationSummary,
  type FineTunedModel,
  type RunDataset,
  type RunProgress,
  type RunStage,
  type TaskRow,
  type TrainingRunEvent,
  type TrainingRunEventPayload,
  type TrainingRunRow,
} from "@/store/fine-tuning-types";
import {
  DAY_MS,
  MINUTE_MS,
  MOCK_MEMBER_EMAIL,
  WORKSPACE_ID,
  costNanoUsd,
  fakeDigest,
  isoAt,
  round3,
  seededRandom,
} from "@/store/mock-values";

const SEEDED_TICK_MS = 9 * MINUTE_MS;
const MAX_REPLAY_TICKS = 50;

const TRAINING_GPU = { type: "NVIDIA H200 141GB", count: 8 } as const;
const PRIMARY_HOST = "h200-nbs-03";
const SECONDARY_HOST = "h200-nbs-07";
const TRAINER_IMAGE = "sha256:4c1e…9b0f";
const RECIPE = "grpo-lora-v1";
const RUNNER = "nomad";

const TOTAL_STEPS = 640;
const STEP_SHARE_PER_TICK = 0.22;
const ADAPTER_SIZE_BYTES = 231_735_296;
const MANIFEST_SIZE_BYTES = 4_812;
const INELIGIBLE_TRACES = 41;

const INITIAL_PROGRESS: RunProgress = {
  step: 0,
  total_steps: TOTAL_STEPS,
  loss: 0.9,
  mean_reward: 0.41,
  tokens_per_second: 1312,
  eta_seconds: 620,
};

const TRAINER_STARTED: TrainingRunEventPayload = {
  type: "trainer_started",
  gpu: TRAINING_GPU,
  image_digest: TRAINER_IMAGE,
  recipe: RECIPE,
};

const capacityGranted = (hostId: string): TrainingRunEventPayload => ({
  type: "capacity_granted",
  host_id: hostId,
  gpu: TRAINING_GPU,
});

const jobSubmitted = (
  providerJobId: string,
  hostId: string,
): TrainingRunEventPayload => ({
  type: "job_submitted",
  runner: RUNNER,
  provider_job_id: providerJobId,
  host_id: hostId,
  gpu: TRAINING_GPU,
});

const versionIdFor = (slug: string, at: string) =>
  `${slug}-${at.slice(0, 10).replace(/-/g, "")}`;

const uniqueVersionId = (
  slug: string,
  at: string,
  existingIds: readonly string[],
) => {
  const base = versionIdFor(slug, at);
  const clashes = existingIds.filter(
    (id) => id === base || id.startsWith(`${base}-`),
  ).length;

  return clashes ? `${base}-${clashes + 1}` : base;
};

const buildDataset = (
  runId: string,
  usable: number,
  newestTraceAt: number,
): RunDataset => {
  const holdout = Math.round(usable * 0.1);
  const validation = Math.round((usable - holdout) * 0.05);

  return {
    oldest_trace_at: isoAt(newestTraceAt - 30 * DAY_MS),
    newest_trace_at: isoAt(newestTraceAt),
    usable,
    deduplicated: usable,
    train: usable - holdout - validation,
    validation,
    holdout,
    train_sha256: fakeDigest(`${runId}-train`),
    holdout_sha256: fakeDigest(`${runId}-holdout`),
  };
};

export interface RunContext {
  now: string;
  random: () => number;
  task: TaskRow;
  judge: EvaluationJudge;
  existingIds: readonly string[];
}

const buildEvaluation = (
  run: TrainingRunRow,
  holdout: number,
  { task, judge, random }: Pick<RunContext, "task" | "judge" | "random">,
): EvaluationSummary => {
  const quality = random();
  const win = round3(0.3 + 0.14 * quality);
  const tie = round3(0.28 + 0.06 * quality);
  const unresolved = round3(0.08 - 0.03 * quality);

  return {
    holdout_groups: Math.max(1, Math.round(holdout / 3.2)),
    holdout_examples: holdout,
    comparison_model_id: task.comparison_model_id,
    judge_model_id: judge,
    vs_comparison: {
      comparator_model_id: task.comparison_model_id,
      win,
      tie,
      loss: round3(1 - win - tie - unresolved),
      unresolved,
    },
    cost_per_request_nano_usd: {
      fine_tuned: costNanoUsd(run.base_model_id, 150, 46),
      comparison: costNanoUsd(task.comparison_model_id, 150, 46),
    },
    output_tokens_per_second: {
      fine_tuned: 112,
      comparison: task.comparison_model_id.startsWith("claude") ? 58 : 71,
    },
    error_rate: round3(0.04 - 0.03 * quality),
  };
};

const adapterFor = (modelId: string): AdapterArtifact => ({
  format: "peft_lora",
  artifact_uri: `s3://gradiated-prod-artifacts-us-east-1/adapters/${modelId}/adapter.tar.gz`,
  sha256: fakeDigest(`${modelId}-adapter`),
  size_bytes: ADAPTER_SIZE_BYTES,
  rank: 16,
  name: modelId,
  source: "trained",
});

const runLogWriter = (log: readonly TrainingRunEvent[]) => {
  const events: TrainingRunEvent[] = [];
  let seq = log.at(-1)?.seq ?? 0;
  let attempt = log.at(-1)?.attempt ?? 1;

  const writer =
    (source: TrainingRunEvent["source"]) =>
    (payload: TrainingRunEventPayload, at: string) => {
      seq += 1;
      events.push({ schema_version: 1, attempt, seq, at, source, ...payload });
    };

  return {
    events,
    controlPlane: writer("control_plane"),
    trainer: writer("trainer"),
    retry: () => {
      attempt += 1;
    },
  };
};

const runCreated = (
  task: TaskRow,
  trigger: TrainingRunRow["trigger"],
): TrainingRunEventPayload => {
  const created = {
    type: "run_created",
    task_id: task.id,
    base_model_id: task.base_model_id,
  } as const;

  return trigger === "manual"
    ? { ...created, trigger, requested_by: MOCK_MEMBER_EMAIL }
    : { ...created, trigger };
};

export const newRun = (
  task: TaskRow,
  trigger: TrainingRunRow["trigger"],
  id: string,
  createdAt: string,
): { run: TrainingRunRow; log: TrainingRunEvent[] } => {
  const writer = runLogWriter([]);

  writer.controlPlane(runCreated(task, trigger), createdAt);
  writer.controlPlane({ type: "stage_entered", stage: "queued" }, createdAt);

  return {
    run: {
      id,
      workspace_id: WORKSPACE_ID,
      task_id: task.id,
      trigger,
      base_model_id: task.base_model_id,
      stage: "queued",
      dataset: null,
      evaluation: null,
      provider_job_id: null,
      created_at: createdAt,
    },
    log: writer.events,
  };
};

export interface RunAdvance {
  run: TrainingRunRow;
  log: TrainingRunEvent[];
  published: FineTunedModel | null;
}

const reservedModelId = (log: readonly TrainingRunEvent[]) => {
  const reserved = log.find((event) => event.type === "model_reserved");

  return reserved?.type === "model_reserved" ? reserved.model_id : null;
};

export const advanceRun = (
  run: TrainingRunRow,
  log: readonly TrainingRunEvent[],
  context: RunContext,
): RunAdvance => {
  const { now, random, task, existingIds } = context;
  const writer = runLogWriter(log);
  const controlPlane = (payload: TrainingRunEventPayload) =>
    writer.controlPlane(payload, now);
  const trainer = (payload: TrainingRunEventPayload) =>
    writer.trainer(payload, now);
  const enter = (stage: RunStage) =>
    controlPlane({ type: "stage_entered", stage });

  const advance = (
    changes: Partial<TrainingRunRow>,
    published: FineTunedModel | null = null,
  ): RunAdvance => ({
    run: { ...run, ...changes },
    log: [...log, ...writer.events],
    published,
  });

  const fail = () => {
    enter("failed");
    controlPlane({
      type: "run_finished",
      stage: "failed",
      error_code: "internal",
    });

    return advance({ stage: "failed" });
  };

  switch (run.stage) {
    case "cancelling": {
      enter("cancelled");
      controlPlane({ type: "run_finished", stage: "cancelled" });

      return advance({ stage: "cancelled" });
    }

    case "queued": {
      enter("building_dataset");

      return advance({ stage: "building_dataset" });
    }

    case "building_dataset": {
      const dataset = buildDataset(
        run.id,
        520 + Math.round(random() * 60),
        Date.parse(now),
      );

      controlPlane({
        type: "note",
        level: "info",
        message: `scanned ${dataset.usable + INELIGIBLE_TRACES} captured requests since the last run, ${dataset.usable} eligible (${INELIGIBLE_TRACES} dropped: truncated or outcome unknown)`,
      });
      controlPlane({ type: "dataset_built", ...dataset });
      enter("awaiting_capacity");

      return advance({ stage: "awaiting_capacity", dataset });
    }

    case "awaiting_capacity": {
      const providerJobId = `training-${run.id.slice(-6)}-1`;

      controlPlane(capacityGranted(PRIMARY_HOST));
      enter("training");
      controlPlane({
        type: "model_reserved",
        model_id: uniqueVersionId(task.slug, now, existingIds),
      });
      controlPlane(jobSubmitted(providerJobId, PRIMARY_HOST));
      trainer(TRAINER_STARTED);
      trainer({ type: "trainer_stage", stage: "preparing_data" });
      trainer({ type: "trainer_stage", stage: "training" });
      trainer({ type: "trainer_progress", ...INITIAL_PROGRESS });

      return advance({ stage: "training", provider_job_id: providerJobId });
    }

    case "training": {
      const previous = runProgress(log) ?? INITIAL_PROGRESS;
      const step = Math.min(
        previous.total_steps,
        previous.step + Math.round(previous.total_steps * STEP_SHARE_PER_TICK),
      );
      const reports = log.filter((event) => event.type === "trainer_progress");

      trainer({
        type: "trainer_progress",
        step,
        total_steps: previous.total_steps,
        loss: Math.max(0.16, round3(previous.loss * 0.82)),
        mean_reward: Math.min(0.86, round3(previous.mean_reward + 0.09)),
        tokens_per_second: previous.tokens_per_second,
        eta_seconds: Math.max(0, Math.round(previous.eta_seconds * 0.55)),
      });
      if (reports.length % 2 === 0) {
        trainer({
          type: "trainer_checkpoint",
          step,
          sha256: fakeDigest(`${run.id}-checkpoint-${step}`),
        });
      }

      if (step < previous.total_steps) return advance({});

      trainer({ type: "trainer_stage", stage: "uploading" });
      trainer({
        type: "trainer_artifact_uploaded",
        name: "adapter.tar.gz",
        sha256: fakeDigest(`${run.id}-adapter`),
        size_bytes: ADAPTER_SIZE_BYTES,
      });
      trainer({
        type: "trainer_artifact_uploaded",
        name: "manifest.json",
        sha256: fakeDigest(`${run.id}-manifest`),
        size_bytes: MANIFEST_SIZE_BYTES,
      });
      trainer({
        type: "trainer_finished",
        manifest_sha256: fakeDigest(`${run.id}-manifest`),
      });
      controlPlane({ type: "job_status", state: "complete" });
      enter("verifying");

      return advance({ stage: "verifying" });
    }

    case "verifying": {
      const modelId = reservedModelId(log);
      if (!modelId) return fail();

      controlPlane({
        type: "artifact_verified",
        model_id: modelId,
        sha256: fakeDigest(`${run.id}-adapter`),
        size_bytes: ADAPTER_SIZE_BYTES,
      });
      enter("publishing");

      return advance({ stage: "publishing" });
    }

    case "publishing": {
      const modelId = reservedModelId(log);
      if (!modelId || !run.dataset) return fail();

      controlPlane({ type: "adapter_loaded", host_id: PRIMARY_HOST });
      controlPlane({ type: "adapter_loaded", host_id: SECONDARY_HOST });
      controlPlane({ type: "published", model_id: modelId });
      enter("evaluating");

      // Publication makes a version callable by its exact id before evaluation.
      return advance(
        { stage: "evaluating" },
        {
          id: modelId,
          status: "available",
          trainable: false,
          workspace_id: run.workspace_id,
          task_id: run.task_id,
          base_model_id: run.base_model_id,
          training_run_id: run.id,
          adapter: adapterFor(modelId),
          created_at: now,
        },
      );
    }

    case "evaluating": {
      if (!run.dataset) return fail();

      const summary = buildEvaluation(run, run.dataset.holdout, context);
      const { win, tie, loss, unresolved } = summary.vs_comparison;

      controlPlane({
        type: "evaluation_progress",
        completed: summary.holdout_examples,
        total: summary.holdout_examples,
      });
      controlPlane({
        type: "evaluation_completed",
        judge: summary.judge_model_id,
        groups: summary.holdout_groups,
        win,
        tie,
        loss,
        unresolved,
      });
      enter("succeeded");
      controlPlane({ type: "run_finished", stage: "succeeded" });

      return advance({ stage: "succeeded", evaluation: summary });
    }

    case "succeeded":
    case "failed":
    case "cancelled":
      return advance({});
  }
};

export const replaySucceededRun = ({
  task,
  trigger,
  runId,
  startedAt,
  judge,
  existingIds,
}: Omit<RunContext, "now" | "random"> & {
  trigger: TrainingRunRow["trigger"];
  runId: string;
  startedAt: number;
}): RunAdvance => {
  let replay: RunAdvance = {
    ...newRun(task, trigger, runId, isoAt(startedAt)),
    published: null,
  };
  const random = seededRandom(runId);

  for (
    let tick = 1;
    tick <= MAX_REPLAY_TICKS && !isTerminalStage(replay.run.stage);
    tick++
  ) {
    const next = advanceRun(replay.run, replay.log, {
      now: isoAt(startedAt + tick * SEEDED_TICK_MS),
      random,
      task,
      judge,
      existingIds,
    });

    replay = { ...next, published: next.published ?? replay.published };
  }

  return replay;
};

export const replayFailedRun = (
  task: TaskRow,
  runId: string,
  startedAt: number,
): { run: TrainingRunRow; log: TrainingRunEvent[] } => {
  const { run, log } = newRun(task, "manual", runId, isoAt(startedAt));
  const dataset = buildDataset(runId, 210, startedAt);
  const firstJob = `training-${runId.slice(-6)}-1`;
  const retryJob = `training-${runId.slice(-6)}-2`;
  const writer = runLogWriter(log);
  const at = (minute: number) => isoAt(startedAt + minute * MINUTE_MS);
  const controlPlane = (minute: number, payload: TrainingRunEventPayload) =>
    writer.controlPlane(payload, at(minute));
  const trainer = (minute: number, payload: TrainingRunEventPayload) =>
    writer.trainer(payload, at(minute));
  const progress = (report: number): TrainingRunEventPayload => ({
    type: "trainer_progress",
    step: Math.round((TOTAL_STEPS * (report + 1)) / 10),
    total_steps: TOTAL_STEPS,
    loss: round3(0.9 * 0.84 ** (report + 1)),
    mean_reward: round3(0.41 + 0.045 * (report + 1)),
    tokens_per_second: INITIAL_PROGRESS.tokens_per_second,
    eta_seconds: (9 - report) * 360,
  });

  controlPlane(8, { type: "stage_entered", stage: "building_dataset" });
  controlPlane(8.2, { type: "dataset_built", ...dataset });
  controlPlane(16, { type: "stage_entered", stage: "awaiting_capacity" });
  controlPlane(16.2, capacityGranted(SECONDARY_HOST));
  controlPlane(24, { type: "stage_entered", stage: "training" });
  controlPlane(24.1, jobSubmitted(firstJob, SECONDARY_HOST));
  trainer(25, TRAINER_STARTED);
  trainer(25.5, { type: "trainer_stage", stage: "training" });
  trainer(26, progress(0));
  trainer(32, progress(1));
  trainer(32.1, {
    type: "trainer_checkpoint",
    step: 128,
    sha256: fakeDigest(`${runId}-checkpoint-128`),
  });
  controlPlane(35, { type: "job_status", state: "lost" });
  controlPlane(35.1, {
    type: "note",
    level: "warning",
    message: `host ${SECONDARY_HOST} stopped reporting; retrying once from the step-128 checkpoint on another host`,
  });

  writer.retry();
  controlPlane(36, capacityGranted(PRIMARY_HOST));
  controlPlane(36.1, jobSubmitted(retryJob, PRIMARY_HOST));
  trainer(37, TRAINER_STARTED);
  trainer(38, { type: "trainer_stage", stage: "training" });
  trainer(44, progress(2));
  trainer(50, progress(3));
  trainer(55, {
    type: "trainer_failed",
    error_code: "deadline",
    message: "attempt deadline reached at step 256 of 640",
  });
  controlPlane(55.1, { type: "job_status", state: "failed" });
  controlPlane(56, { type: "stage_entered", stage: "failed" });
  controlPlane(56.1, {
    type: "run_finished",
    stage: "failed",
    error_code: "attempt_deadline",
    message: "The training attempt did not finish within its deadline.",
  });

  return {
    run: { ...run, stage: "failed", dataset, provider_job_id: retryJob },
    log: [...log, ...writer.events],
  };
};

export const requestCancel = (
  run: TrainingRunRow,
  log: readonly TrainingRunEvent[],
  at: string,
): { run: TrainingRunRow; log: TrainingRunEvent[] } => {
  const writer = runLogWriter(log);

  writer.controlPlane(
    { type: "cancel_requested", requested_by: MOCK_MEMBER_EMAIL },
    at,
  );
  writer.controlPlane({ type: "stage_entered", stage: "cancelling" }, at);

  return {
    run: { ...run, stage: "cancelling" },
    log: [...log, ...writer.events],
  };
};
