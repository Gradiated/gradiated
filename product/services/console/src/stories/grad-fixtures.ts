import type {
  Artifact,
  Checkpoint,
  Dataset,
  DatasetRecord,
  EvalRun,
  EvalTaskOutcome,
  ImportJob,
  PlanRunResponse,
  ResolvedRunConfig,
  Run,
  RunEvent,
  Source,
  TrainableModel,
} from "@/lib/grad/types";

const workspaceId = "00000000-0000-4000-8000-000000000002";
const day = (date: string, time = "12:00:00") => `2026-11-${date}T${time}Z`;
const minutes = (start: string, offset: number) =>
  new Date(Date.parse(start) + offset * 60_000).toISOString();

export const baseModels: TrainableModel[] = [
  {
    id: "qwen3-8b",
    hfRepo: "Qwen/Qwen3-8B",
    family: "llm",
    adapters: ["lora"],
    recipes: ["sft", "dpo", "distill", "decision", "reward", "cartridge"],
    defaultFor: ["sft", "dpo", "distill"],
    pricePerMillionTokensUsd: 2,
    maxContextTokens: 32_768,
    templateRevision: "qwen3-2026-10",
    calibratedLrs: { sft: 0.0002 },
    minGpuMemoryGb: 38,
  },
  {
    id: "qwen3-1.7b",
    hfRepo: "Qwen/Qwen3-1.7B",
    family: "llm",
    adapters: ["lora", "frozen_head"],
    recipes: [
      "sft",
      "dpo",
      "router",
      "decision",
      "reward",
      "cartridge",
      "distill",
    ],
    defaultFor: ["router", "decision", "reward", "cartridge"],
    pricePerMillionTokensUsd: 0.6,
    maxContextTokens: 32_768,
    templateRevision: "qwen3-2026-10",
    calibratedLrs: {},
    minGpuMemoryGb: 14,
  },
  {
    id: "bge-base-en-v1.5",
    hfRepo: "BAAI/bge-base-en-v1.5",
    family: "encoder",
    adapters: ["encoder_full"],
    recipes: ["embedding"],
    defaultFor: ["embedding"],
    pricePerMillionTokensUsd: 0.1,
    maxContextTokens: 512,
    templateRevision: "bge-2026-09",
    calibratedLrs: {},
    minGpuMemoryGb: 4,
  },
];

const resolvedConfig = (
  name: string,
  dataset: string,
  kind: Run["recipeKind"],
  model: string,
): ResolvedRunConfig => ({
  ruleVersion: "2026-11",
  dataset,
  datasetVersion: 3,
  name,
  recipeKind: kind,
  model,
  templateRevision: "qwen3-2026-10",
  adapter: { kind: "lora", rank: 32, alpha: 64 },
  lr: 0.0002,
  lrSource: "calibrated",
  batchSize: 16,
  epochs: 2,
  schedule: "cosine",
  warmup: 0.05,
  trainOn: "all_assistant",
  thinking: "auto",
  preserveThinking: false,
  reduction: "per_example",
  select: "best",
  checkpointEverySteps: 100,
  evalEverySteps: 200,
  optimizer: { kind: "adamw" },
  checkpointTtlDays: 30,
  split: {
    strategy: "by_session",
    evalFraction: 0.05,
    seed: 0,
    trainRecords: 11_856,
    evalRecords: 624,
  },
  labelEvalId: null,
  baseArtifact: null,
  recipeParams: {},
});

const metric = (step: number, attempt: number, start: string) => {
  const loss = 0.42 + 1.1 * Math.exp(-step / 420) + 0.03 * Math.sin(step / 37);
  const evalStep = step % 200 === 0;

  return {
    seq: 0,
    attempt,
    step,
    loss: Number(loss.toFixed(4)),
    ...(evalStep
      ? {
          evalLoss: Number((loss + 0.06).toFixed(4)),
          evalMetrics: {
            eval_loss: Number((loss + 0.06).toFixed(4)),
            eval_token_accuracy: Number(
              (0.58 + 0.25 * (1 - Math.exp(-step / 500))).toFixed(4),
            ),
          },
        }
      : {}),
    gradNorm: 0.8,
    lr: 0.0002,
    tokensPerSec: 4_200,
    tokens: step * 4_096,
    costUsd: Number(((step * 4_096 * 2) / 1_000_000).toFixed(4)),
    timestamp: minutes(start, step / 8),
  };
};

const runBase = {
  workspaceId,
  datasetId: "ds_support",
  datasetVersion: 3,
  maxCostUsd: null,
  pricePerMillionTokens: 2,
  maxAttempts: 3,
  phaseSince: null,
  lastInterruption: null,
  workersOnline: null,
  autoscaling: null,
  queuePosition: null,
  queueMessage: null,
  minGpuMemoryGb: 38,
  latestMetric: null,
  evalReport: null,
  checkpointEvals: [],
  artifactId: null,
  error: null,
  finishedAt: null,
} satisfies Partial<Run>;

export const runningRun: Run = {
  ...runBase,
  id: "run_01jdx3k8q2support",
  name: "support-sft",
  datasetName: "support-traces",
  recipeKind: "sft",
  status: "running",
  resolvedConfig: resolvedConfig(
    "support-sft",
    "support-traces",
    "sft",
    "qwen3-8b",
  ),
  maxCostUsd: 20,
  tokensProcessed: 1240 * 4096,
  costUsd: 10.16,
  currentStep: 1240,
  totalSteps: 2000,
  attempt: 2,
  phase: "training",
  phaseSince: day("26", "10:54:00"),
  lastInterruption: {
    attempt: 1,
    reason: "compute_reclaimed",
    step: 860,
    resumeStep: 800,
    at: day("26", "10:48:00"),
    message:
      "The GPU was reclaimed; the worker saved a checkpoint and handed the run back.",
  },
  latestMetric: metric(1240, 2, day("26", "09:00:00")),
  createdAt: day("26", "08:58:00"),
  updatedAt: day("26", "10:35:00"),
};

export const completedRun: Run = {
  ...runBase,
  id: "run_01jdw9p0m4prefs",
  name: "support-dpo",
  datasetName: "support-prefs",
  datasetId: "ds_prefs",
  datasetVersion: 1,
  recipeKind: "dpo",
  status: "completed",
  resolvedConfig: resolvedConfig(
    "support-dpo",
    "support-prefs",
    "dpo",
    "qwen3-8b",
  ),
  tokensProcessed: 600 * 4096,
  costUsd: 4.92,
  currentStep: 600,
  totalSteps: 600,
  attempt: 1,
  phase: "completing",
  latestMetric: metric(600, 1, day("24", "14:00:00")),
  evalReport: {
    metricName: "preference_accuracy",
    metricMode: "max",
    selectedStep: 400,
    bestStep: 400,
    finalStep: 600,
    trainRecords: 3_420,
    evalRecords: 180,
    warnings: [
      "12 pairs had identical chosen and rejected answers and were dropped.",
    ],
    preferenceAccuracy: 0.812,
    rewardMargin: 1.94,
    evalLoss: 0.4113,
    beta: 0.1,
    trainPairs: 3_408,
    evalPairs: 180,
    droppedRecords: 12,
  },
  checkpointEvals: [
    {
      name: "support-holdout",
      step: 400,
      checkpointId: "ckpt_prefs_400",
      evalId: "ev_01jdwholdout",
      dataset: "support-holdout",
      datasetVersion: 1,
      status: "completed",
      score: 0.774,
      costUsd: 0.38,
      error: null,
    },
  ],
  artifactId: "support-dpo@2026-11-24-1",
  createdAt: day("24", "13:58:00"),
  updatedAt: day("24", "15:21:00"),
  finishedAt: day("24", "15:21:00"),
};

export const queuedRun: Run = {
  ...runBase,
  id: "run_01jdx5r7router",
  name: "router-v2",
  datasetName: "support-traces",
  recipeKind: "router",
  status: "queued",
  resolvedConfig: resolvedConfig(
    "router-v2",
    "support-traces",
    "router",
    "qwen3-1.7b",
  ),
  tokensProcessed: 0,
  costUsd: 0,
  currentStep: 0,
  totalSteps: 900,
  attempt: 0,
  phase: "waiting_for_compute",
  phaseSince: day("26", "10:30:00"),
  workersOnline: 2,
  autoscaling: false,
  queuePosition: 3,
  queueMessage: "Queued behind 3 runs",
  minGpuMemoryGb: 12,
  createdAt: day("26", "10:24:00"),
  updatedAt: day("26", "10:30:00"),
};

export const stoppedRun: Run = {
  ...runBase,
  id: "run_01jdv2cartridge",
  name: "faq-cartridge",
  datasetName: "faq-docs",
  recipeKind: "cartridge",
  status: "stopped_budget",
  resolvedConfig: resolvedConfig(
    "faq-cartridge",
    "faq-docs",
    "cartridge",
    "qwen3-1.7b",
  ),
  maxCostUsd: 5,
  tokensProcessed: 8_300_000,
  costUsd: 5,
  currentStep: 410,
  totalSteps: 700,
  attempt: 1,
  phase: "training",
  createdAt: day("22", "09:10:00"),
  updatedAt: day("22", "11:02:00"),
  finishedAt: day("22", "11:02:00"),
};

export const failedRun: Run = {
  ...runBase,
  id: "run_01jdu8decision",
  name: "triage-decision",
  datasetName: "support-traces",
  recipeKind: "decision",
  status: "failed",
  resolvedConfig: resolvedConfig(
    "triage-decision",
    "support-traces",
    "decision",
    "qwen3-1.7b",
  ),
  tokensProcessed: 1_200_000,
  costUsd: 0.72,
  currentStep: 140,
  totalSteps: 800,
  attempt: 3,
  phase: "training",
  error:
    "The run ran out of GPU memory on 3 attempts. Lower batch_size or use a smaller base model.",
  createdAt: day("21", "16:40:00"),
  updatedAt: day("21", "17:25:00"),
  finishedAt: day("21", "17:25:00"),
};

export const runs = [
  runningRun,
  queuedRun,
  completedRun,
  stoppedRun,
  failedRun,
];

const buildEvents = (
  run: Run,
  start: string,
  finished: boolean,
): RunEvent[] => {
  const events: RunEvent[] = [];
  const push = (event: Record<string, unknown>) =>
    events.push({
      ...event,
      runId: run.id,
      seq: events.length + 1,
    } as RunEvent);
  const at = (offset: number) => minutes(start, offset);

  push({
    type: "phase",
    attempt: 1,
    timestamp: at(0),
    phase: "queued",
    step: 0,
    workersOnline: null,
    autoscaling: null,
    queuePosition: null,
    message: null,
    gpu: null,
  });
  push({
    type: "attempt",
    attempt: 1,
    timestamp: at(1),
    event: "started",
    reason: null,
    step: null,
    resumeStep: null,
    maxAttempts: 3,
    message: "",
  });
  push({
    type: "phase",
    attempt: 1,
    timestamp: at(1),
    phase: "starting",
    step: 0,
    workersOnline: null,
    autoscaling: null,
    queuePosition: null,
    message: null,
    gpu: { name: "NVIDIA H100 80GB", memoryGb: 80 },
  });
  push({
    type: "phase",
    attempt: 1,
    timestamp: at(2),
    phase: "loading_model",
    step: 0,
    workersOnline: null,
    autoscaling: null,
    queuePosition: null,
    message: null,
    gpu: null,
  });
  push({
    type: "phase",
    attempt: 1,
    timestamp: at(4),
    phase: "training",
    step: 0,
    workersOnline: null,
    autoscaling: null,
    queuePosition: null,
    message: null,
    gpu: null,
  });

  const interruptedAt = run.attempt > 1 ? 860 : Infinity;
  const lastStep = finished ? run.totalSteps : run.currentStep;

  for (let step = 20; step <= Math.min(lastStep, interruptedAt); step += 20) {
    const point = metric(step, 1, start);
    push({
      type: "metric",
      attempt: 1,
      timestamp: point.timestamp,
      step,
      metric: { ...point, seq: events.length + 1 },
    });
    if (step % 200 === 0)
      push({
        type: "checkpoint",
        attempt: 1,
        timestamp: point.timestamp,
        step,
        checkpointId: `ckpt_${run.id}_${step}`,
        evalScore: point.evalLoss ?? null,
        format: "peft_lora",
      });
  }

  if (run.attempt > 1) {
    push({
      type: "attempt",
      attempt: 1,
      timestamp: at(110),
      event: "interrupted",
      reason: "compute_reclaimed",
      step: 860,
      resumeStep: 800,
      maxAttempts: 3,
      message: "",
    });
    push({
      type: "phase",
      attempt: 2,
      timestamp: at(112),
      phase: "queued",
      step: 800,
      workersOnline: null,
      autoscaling: true,
      queuePosition: null,
      message: null,
      gpu: null,
    });
    push({
      type: "attempt",
      attempt: 2,
      timestamp: at(114),
      event: "started",
      reason: null,
      step: null,
      resumeStep: 800,
      maxAttempts: 3,
      message: "",
    });
    push({
      type: "phase",
      attempt: 2,
      timestamp: at(114),
      phase: "starting",
      step: 800,
      workersOnline: null,
      autoscaling: null,
      queuePosition: null,
      message: null,
      gpu: { name: "NVIDIA H100 80GB", memoryGb: 80 },
    });
    push({
      type: "phase",
      attempt: 2,
      timestamp: at(116),
      phase: "training",
      step: 800,
      workersOnline: null,
      autoscaling: null,
      queuePosition: null,
      message: null,
      gpu: null,
    });

    for (let step = 820; step <= lastStep; step += 20) {
      const point = metric(step, 2, start);
      push({
        type: "metric",
        attempt: 2,
        timestamp: at(116 + (step - 800) / 8),
        step,
        metric: { ...point, attempt: 2, seq: events.length + 1 },
      });
      if (step % 200 === 0)
        push({
          type: "checkpoint",
          attempt: 2,
          timestamp: at(116 + (step - 800) / 8),
          step,
          checkpointId: `ckpt_${run.id}_${step}`,
          evalScore: point.evalLoss ?? null,
          format: "peft_lora",
        });
    }
  }

  if (finished) {
    push({
      type: "phase",
      attempt: run.attempt,
      timestamp: at(80),
      phase: "uploading",
      step: lastStep,
      workersOnline: null,
      autoscaling: null,
      queuePosition: null,
      message: null,
      gpu: null,
    });
    push({
      type: "phase",
      attempt: run.attempt,
      timestamp: at(82),
      phase: "completing",
      step: lastStep,
      workersOnline: null,
      autoscaling: null,
      queuePosition: null,
      message: null,
      gpu: null,
    });
    events.push({
      type: "completed",
      runId: run.id,
      seq: events.length,
      attempt: run.attempt,
      timestamp: at(83),
      status: run.status,
      run,
    } as RunEvent);
  }

  return events;
};

export const runEvents: Record<string, RunEvent[]> = {
  [runningRun.id]: buildEvents(runningRun, day("26", "08:58:00"), false),
  [completedRun.id]: buildEvents(completedRun, day("24", "13:58:00"), true),
  [queuedRun.id]: [
    {
      type: "phase",
      runId: queuedRun.id,
      seq: 1,
      attempt: 0,
      timestamp: day("26", "10:24:00"),
      phase: "queued",
      step: 0,
      workersOnline: 2,
      autoscaling: false,
      queuePosition: null,
      message: null,
      gpu: null,
    },
    {
      type: "phase",
      runId: queuedRun.id,
      seq: 2,
      attempt: 0,
      timestamp: day("26", "10:30:00"),
      phase: "waiting_for_compute",
      step: 0,
      workersOnline: 2,
      autoscaling: false,
      queuePosition: null,
      message: null,
      gpu: null,
    },
  ],
};

export const checkpoints = (run: Run): Checkpoint[] =>
  (runEvents[run.id] ?? []).flatMap((event) =>
    event.type === "checkpoint"
      ? [
          {
            id: event.checkpointId,
            workspaceId,
            runId: run.id,
            attempt: event.attempt,
            step: event.step,
            evalScore: event.evalScore,
            format: event.format,
            sha256: "9f2c".padEnd(64, "0"),
            sizeBytes: 167_772_160,
            metadata: {},
            best: run.status === "completed" && event.step === 400,
            final: run.status === "completed" && event.step === run.totalSteps,
            expiresAt:
              run.status === "completed" &&
              (event.step === 400 || event.step === run.totalSteps)
                ? null
                : day("30"),
            createdAt: event.timestamp,
          },
        ]
      : [],
  );

export const artifact: Artifact = {
  id: "support-dpo@2026-11-24-1",
  workspaceId,
  name: "support-dpo",
  version: "2026-11-24-1",
  runId: completedRun.id,
  checkpointId: "ckpt_prefs_400",
  baseModel: "qwen3-8b",
  recipeKind: "dpo",
  format: "peft_lora",
  sha256: "4be1d0c3a99f02e6b7c51d8a3f0e6c2b9d8a7f6e5d4c3b2a1908f7e6d5c4b3a2",
  sizeBytes: 167_772_160,
  manifest: {},
  evalReport: completedRun.evalReport,
  provenance: {
    source: "run",
    runId: completedRun.id,
    uploader: null,
    uri: null,
  },
  createdAt: day("24", "15:20:00"),
};

export const datasets: Dataset[] = [
  {
    id: "ds_support",
    workspaceId,
    name: "support-traces",
    version: 3,
    recordCount: 12_480,
    metadata: {},
    createdAt: day("10"),
    updatedAt: day("26", "06:00:00"),
  },
  {
    id: "ds_prefs",
    workspaceId,
    name: "support-prefs",
    version: 1,
    recordCount: 3_600,
    metadata: {},
    createdAt: day("18"),
    updatedAt: day("18"),
  },
  {
    id: "ds_faq",
    workspaceId,
    name: "faq-docs",
    version: 2,
    recordCount: 840,
    metadata: {},
    createdAt: day("12"),
    updatedAt: day("20"),
  },
];

export const records: DatasetRecord[] = [
  [
    "How do I reset my password?",
    "Open Settings → Security and choose Reset password. We email you a link that works for 30 minutes.",
    { resolved: 1, csat: 5 },
  ],
  [
    "Can I change the billing email on my invoices?",
    "Yes. An admin can change it under Billing → Invoices and billing details.",
    { resolved: 1 },
  ],
  [
    "The export to CSV times out for large projects.",
    "Exports over 100k rows run in the background; you get an email with a download link when it is ready.",
    { resolved: 1, csat: 4 },
  ],
  [
    "Why was I charged twice this month?",
    "I'm sorry about that. One charge is a pending authorization that drops off within 3 business days.",
    { resolved: 0 },
  ],
  [
    "Is there an API rate limit?",
    "Yes: 600 requests per minute per key. Responses include X-RateLimit-Remaining.",
    { resolved: 1 },
  ],
  [
    "How do I invite a teammate?",
    "Go to Settings → Members and choose Invite. They join with the Member role by default.",
    { resolved: 1, csat: 5 },
  ],
].map(([question, answer, scores], index) => ({
  id: `rec_${String(index + 1).padStart(4, "0")}`,
  sessionId: `sess_${index + 1}`,
  messages: [
    { role: "system", content: "You are Acme's support assistant." },
    { role: "user", content: question as string },
    { role: "assistant", content: answer as string },
  ],
  scores: scores as Record<string, number>,
  metadata: { model: "gpt-4.1-mini" },
  timestamp: day("25", `0${index}:15:00`),
}));

const sourceLimits = {
  sampleRate: 1,
  maxRecordsPerSync: null,
  maxRecordsPerDay: null,
  recordsToday: 0,
  versionInterval: 900,
  pendingRecords: 0,
} satisfies Partial<Source>;

export const sources: Source[] = [
  {
    id: "src_langfuse",
    workspaceId,
    dataset: "support-traces",
    provider: {
      kind: "langfuse",
      host: "https://cloud.langfuse.com",
      secret: "langfuse-key",
      project: "support-bot",
      filters: {},
    },
    schedule: "0 */6 * * *",
    ...sourceLimits,
    nextSyncAt: day("26", "12:00:00"),
    status: "active",
    pausedReason: null,
    lastError: null,
    lastErrorAt: null,
    consecutiveFailures: 0,
    pendingFull: false,
    lastSyncedAt: day("26", "06:00:40"),
    lastSync: {
      importId: "imp_sync_3",
      status: "completed",
      full: false,
      datasetVersion: 3,
      error: null,
      createdAt: day("26", "06:00:00"),
      finishedAt: day("26", "06:00:40"),
    },
    createdAt: day("10"),
    updatedAt: day("26", "06:00:40"),
  },
  {
    id: "src_posthog",
    workspaceId,
    dataset: "support-traces",
    provider: {
      kind: "posthog",
      host: "https://us.posthog.com",
      secret: "posthog-key",
      project: "48213",
      filters: {},
    },
    schedule: "*/30 * * * *",
    ...sourceLimits,
    nextSyncAt: null,
    status: "paused",
    pausedReason:
      "Paused after 10 failed syncs in a row. Sync now or update the secret to resume.",
    lastError: "PostHog returned 401: the personal API key was revoked.",
    lastErrorAt: day("25", "23:30:00"),
    consecutiveFailures: 10,
    pendingFull: false,
    lastSyncedAt: day("24", "18:30:00"),
    lastSync: {
      importId: "imp_sync_ph",
      status: "failed",
      full: false,
      datasetVersion: null,
      error: "PostHog returned 401: the personal API key was revoked.",
      createdAt: day("25", "23:30:00"),
      finishedAt: day("25", "23:30:05"),
    },
    createdAt: day("15"),
    updatedAt: day("25", "23:30:05"),
  },
];

const importJob = (
  patch: Partial<ImportJob> &
    Pick<ImportJob, "id" | "datasetVersion" | "importedCount" | "createdAt">,
): ImportJob => ({
  workspaceId,
  dataset: "support-traces",
  status: "completed",
  source: { kind: "upload", upload_id: "f00d" },
  connector: "openai_chat",
  attempt: 1,
  droppedCount: 0,
  detectedScores: [],
  dropReasons: [],
  error: null,
  updatedAt: patch.createdAt,
  ...patch,
});

export const imports: ImportJob[] = [
  importJob({
    id: "imp_sync_3",
    datasetVersion: 3,
    importedCount: 1_380,
    createdAt: day("26", "06:00:00"),
    source: { kind: "source", source_id: "src_langfuse" },
    connector: "langfuse",
  }),
  importJob({
    id: "imp_sync_2",
    datasetVersion: 2,
    importedCount: 2_100,
    createdAt: day("20", "06:00:00"),
    source: { kind: "source", source_id: "src_langfuse" },
    connector: "langfuse",
  }),
  importJob({
    id: "imp_upload_1",
    datasetVersion: 1,
    importedCount: 9_000,
    droppedCount: 3,
    dropReasons: [
      "line 118: invalid JSON",
      "line 4410: no assistant turn",
      "line 8812: no assistant turn",
    ],
    createdAt: day("10", "09:00:00"),
  }),
];

export const evals: EvalRun[] = [
  {
    id: "ev_01jdx0support",
    workspaceId,
    name: "support-sft-vs-base",
    status: "completed",
    mode: "eval",
    models: ["support-sft@2026-11-24-1", "qwen3-8b", "gpt-4.1-mini"],
    baseline: "gpt-4.1-mini",
    taskSource: { kind: "dataset", dataset: "support-holdout", version: 1 },
    rubric: [
      { name: "helpful", kind: "judge", weight: 2, model: "claude-sonnet-4-5" },
      { name: "non_empty", kind: "validator", validator: "non_empty" },
    ],
    samples: 3,
    temperature: 0.7,
    maxTokens: 1024,
    passThreshold: 0.5,
    judgeModels: ["claude-sonnet-4-5"],
    localScorers: [],
    progress: { totalOutputs: 1_800, generated: 1_800, pendingLocalScores: 0 },
    summary: [
      {
        model: "support-sft@2026-11-24-1",
        overall: 0.842,
        ciLow: 0.818,
        ciHigh: 0.864,
        passAtK: { "1": 0.79, "3": 0.91 },
        vsBaseline: { delta: 0.051, ciLow: 0.021, ciHigh: 0.08 },
        tasks: 600,
        errors: 0,
        tokensPerTask: 212,
        costPer1kTasksUsd: 0.41,
      },
      {
        model: "gpt-4.1-mini",
        overall: 0.791,
        ciLow: 0.765,
        ciHigh: 0.816,
        passAtK: { "1": 0.74, "3": 0.88 },
        vsBaseline: null,
        tasks: 600,
        errors: 2,
        tokensPerTask: 238,
        costPer1kTasksUsd: 1.9,
      },
      {
        model: "qwen3-8b",
        overall: 0.703,
        ciLow: 0.674,
        ciHigh: 0.731,
        passAtK: { "1": 0.63, "3": 0.81 },
        vsBaseline: { delta: -0.088, ciLow: -0.12, ciHigh: -0.057 },
        tasks: 600,
        errors: 0,
        tokensPerTask: 260,
        costPer1kTasksUsd: 0.38,
      },
    ],
    totalCostUsd: 6.84,
    scoredDatasetVersion: null,
    error: null,
    createdAt: day("25", "09:00:00"),
    updatedAt: day("25", "09:42:00"),
    completedAt: day("25", "09:42:00"),
  },
  {
    id: "ev_01jdx6gsm8k",
    workspaceId,
    name: "gsm8k-check",
    status: "running",
    mode: "eval",
    models: ["support-sft@2026-11-24-1"],
    baseline: null,
    taskSource: { kind: "dataset", dataset: "gsm8k-200", version: 1 },
    rubric: [
      { name: "final_number", kind: "validator", validator: "final_number" },
    ],
    samples: 1,
    temperature: 0,
    maxTokens: 512,
    passThreshold: 1,
    judgeModels: [],
    localScorers: [],
    progress: { totalOutputs: 200, generated: 132, pendingLocalScores: 0 },
    summary: [],
    totalCostUsd: 0.06,
    scoredDatasetVersion: null,
    error: null,
    createdAt: day("26", "10:20:00"),
    updatedAt: day("26", "10:31:00"),
    completedAt: null,
  },
];

export const evalFailures: EvalTaskOutcome[] = [
  {
    taskId: "task_0042",
    model: "qwen3-8b",
    score: 0.25,
    passed: false,
    sampleScores: [0, 0.5, 0.25],
    judgeModel: "claude-sonnet-4-5",
    record: records[3] ?? {},
  },
  {
    taskId: "task_0108",
    model: "gpt-4.1-mini",
    score: 0.33,
    passed: false,
    sampleScores: [0.5, 0.5, 0],
    judgeModel: "claude-sonnet-4-5",
    record: records[2] ?? {},
  },
  {
    taskId: "task_0311",
    model: "support-sft@2026-11-24-1",
    score: 0.42,
    passed: false,
    sampleScores: [0.5, 0.25, 0.5],
    judgeModel: "claude-sonnet-4-5",
    record: records[1] ?? {},
  },
];

export const plan: PlanRunResponse = {
  resolvedConfig: resolvedConfig(
    "support-traces-sft",
    "support-traces",
    "sft",
    "qwen3-8b",
  ),
  datasetVersion: 3,
  usableRecords: 12_402,
  totalRecords: 12_480,
  estimatedSteps: 1_550,
  estimatedTokens: 25_400_000,
  estimatedCostUsd: 50.8,
  costBreakdown: { trainUsd: 50.8, teacherUsd: 0, evalUsd: 0 },
  estimatedDurationS: 6_900,
  minGpuMemoryGb: 38,
  pricePerMillionTokens: 2,
  trainedTokenFraction: 0.41,
  labeling: null,
  teacher: null,
  warnings: ["78 records have no assistant turn and are skipped."],
};

export const usageSummary = (groupBy: string) => {
  const daily = [3.2, 0, 12.4, 8.1, 0.9, 22.6, 14.3, 5.8, 0, 31.2, 18.7, 9.4];
  const groups =
    groupBy === "model"
      ? [
          { key: "qwen3-8b", cost_usd: 98.4, tokens: 49_200_000, records: 410 },
          {
            key: "qwen3-1.7b",
            cost_usd: 21.6,
            tokens: 36_000_000,
            records: 120,
          },
          {
            key: "gpt-4.1-mini",
            cost_usd: 6.6,
            tokens: 3_100_000,
            records: 18,
          },
        ]
      : groupBy === "recipe"
        ? [
            { key: "sft", cost_usd: 71.2, tokens: 35_600_000, records: 300 },
            { key: "dpo", cost_usd: 27.2, tokens: 13_600_000, records: 110 },
            {
              key: "cartridge",
              cost_usd: 21.6,
              tokens: 36_000_000,
              records: 120,
            },
            { key: null, cost_usd: 6.6, tokens: 3_100_000, records: 18 },
          ]
        : groupBy === "kind"
          ? [
              {
                key: "training",
                cost_usd: 118.8,
                tokens: 84_600_000,
                records: 520,
              },
              { key: "eval", cost_usd: 6.84, tokens: 3_000_000, records: 24 },
              { key: "labeling", cost_usd: 0.96, tokens: 700_000, records: 4 },
            ]
          : daily.map((cost, index) => ({
              key: `2026-11-${String(index * (groupBy === "week" ? 7 : 2) + 1).padStart(2, "0")}`,
              cost_usd: cost,
              tokens: Math.round(cost * 500_000),
              records: Math.round(cost * 4),
            }));

  return {
    from: "2026-11-01T00:00:00Z",
    to: "2026-11-27T00:00:00Z",
    cost_usd: 126.6,
    tokens: 88_300_000,
    records: 548,
    by_kind: [
      { kind: "training", cost_usd: 118.8, tokens: 84_600_000, records: 520 },
      { kind: "eval", cost_usd: 6.84, tokens: 3_000_000, records: 24 },
      { kind: "labeling", cost_usd: 0.96, tokens: 700_000, records: 4 },
    ],
    top_runs: [
      {
        id: runningRun.id,
        name: runningRun.name,
        kind: "training",
        cost_usd: 61.4,
        tokens: 30_700_000,
      },
      {
        id: completedRun.id,
        name: completedRun.name,
        kind: "training",
        cost_usd: 27.2,
        tokens: 13_600_000,
      },
      {
        id: stoppedRun.id,
        name: stoppedRun.name,
        kind: "training",
        cost_usd: 21.6,
        tokens: 36_000_000,
      },
    ],
    top_evals: [
      {
        id: "ev_01jdx0support",
        name: "support-sft-vs-base",
        kind: "eval",
        cost_usd: 6.84,
        tokens: 3_000_000,
      },
      {
        id: "ev_label_router",
        name: "router-v2-labels",
        kind: "labeling",
        cost_usd: 0.96,
        tokens: 700_000,
      },
    ],
    group_by: groupBy,
    groups,
  };
};
