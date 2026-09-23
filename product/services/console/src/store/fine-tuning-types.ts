export const TRAINING_TRACE_THRESHOLD = 500;

export const EVALUATION_JUDGE_ALLOWLIST = [
  "openai/gpt-5.6-sol",
  "openai/gpt-5",
  "anthropic/claude-fable-5-1",
  "anthropic/claude-opus-5",
  "anthropic/claude-sonnet-5",
] as const;

export type EvaluationJudge = (typeof EVALUATION_JUDGE_ALLOWLIST)[number];

export type WorkspaceRow = Readonly<{
  id: string;
  trace_capture_enabled: boolean;
  evaluation_judge: EvaluationJudge;
}>;

export type AdapterArtifact = Readonly<{
  format: "peft_lora";
  artifact_uri: string;
  sha256: string;
  size_bytes: number;
  rank: number;
  name: string;
  source: "trained" | "uploaded";
}>;

export type CatalogModel = Readonly<{
  id: string;
  status: "available" | "unavailable";
  trainable: boolean;
  workspace_id: null;
  task_id: null;
  base_model_id: null;
  training_run_id: null;
  adapter: null;
  created_at: string;
}>;

export type FineTunedModel = Readonly<{
  id: string;
  status: "available" | "unavailable";
  trainable: false;
  workspace_id: string;
  task_id: string;
  base_model_id: string;
  training_run_id: string;
  adapter: AdapterArtifact;
  created_at: string;
}>;

export type ModelRow = CatalogModel | FineTunedModel;

export const isFineTuned = (model: ModelRow): model is FineTunedModel =>
  model.task_id !== null;

export type TaskRow = Readonly<{
  id: string;
  slug: string;
  base_model_id: string;
  /** A change applies to later runs; each evaluation keeps the comparison model it ran against. */
  comparison_model_id: string;
  production_model_id: string | null;
}>;

export const STAGE_ORDER = [
  "queued",
  "building_dataset",
  "awaiting_capacity",
  "training",
  "verifying",
  "publishing",
  "evaluating",
  "succeeded",
] as const;

export const TERMINAL_STAGES = ["succeeded", "failed", "cancelled"] as const;

export type TerminalStage = (typeof TERMINAL_STAGES)[number];

export type RunStage =
  (typeof STAGE_ORDER)[number] | TerminalStage | "cancelling";

export const isTerminalStage = (stage: RunStage): stage is TerminalStage =>
  TERMINAL_STAGES.some((terminal) => terminal === stage);

export const STAGE_LABEL: Record<RunStage, string> = {
  queued: "Queued",
  building_dataset: "Building dataset",
  awaiting_capacity: "Waiting for capacity",
  training: "Training",
  verifying: "Verifying",
  publishing: "Publishing",
  evaluating: "Evaluating",
  cancelling: "Cancelling",
  succeeded: "Succeeded",
  failed: "Failed",
  cancelled: "Cancelled",
};

export type RunDataset = Readonly<{
  oldest_trace_at: string;
  newest_trace_at: string;
  usable: number;
  deduplicated: number;
  train: number;
  validation: number;
  holdout: number;
  train_sha256: string;
  holdout_sha256: string;
}>;

/** Fractions sum to 1; `unresolved` verdicts are shown but never counted as losses. */
export type JudgeOutcome = Readonly<{
  comparator_model_id: string;
  win: number;
  tie: number;
  loss: number;
  unresolved: number;
}>;

export type EvaluationSummary = Readonly<{
  holdout_groups: number;
  holdout_examples: number;
  comparison_model_id: string;
  judge_model_id: EvaluationJudge;
  vs_comparison: JudgeOutcome;
  cost_per_request_nano_usd: Readonly<{
    fine_tuned: number;
    comparison: number;
  }>;
  output_tokens_per_second: Readonly<{
    fine_tuned: number;
    comparison: number;
  }>;
  error_rate: number;
}>;

export type TrainingRunRow = Readonly<{
  id: string;
  workspace_id: string;
  task_id: string;
  trigger: "automation" | "manual";
  base_model_id: string;
  stage: RunStage;
  dataset: RunDataset | null;
  evaluation: EvaluationSummary | null;
  provider_job_id: string | null;
  created_at: string;
}>;

type EventEnvelope = Readonly<{
  schema_version: 1;
  attempt: number;
  seq: number;
  at: string;
  source: "control_plane" | "trainer";
}>;

export type Gpu = Readonly<{ type: string; count: number }>;

type RunCreated = Readonly<{
  type: "run_created";
  task_id: string;
  base_model_id: string;
}> &
  (
    | Readonly<{ trigger: "manual"; requested_by: string }>
    | Readonly<{ trigger: "automation" }>
  );

export type TrainingRunEventPayload =
  | RunCreated
  | Readonly<{ type: "stage_entered"; stage: RunStage }>
  | Readonly<{ type: "dataset_built" } & RunDataset>
  | Readonly<{ type: "capacity_granted"; host_id: string; gpu: Gpu }>
  | Readonly<{
      type: "job_submitted";
      runner: string;
      provider_job_id: string;
      host_id: string;
      gpu: Gpu;
    }>
  | Readonly<{
      type: "job_status";
      state: "running" | "complete" | "lost" | "failed";
      message?: string;
    }>
  | Readonly<{ type: "model_reserved"; model_id: string }>
  | Readonly<{
      type: "artifact_verified";
      model_id: string;
      sha256: string;
      size_bytes: number;
    }>
  | Readonly<{ type: "adapter_loaded"; host_id: string }>
  | Readonly<{ type: "evaluation_progress"; completed: number; total: number }>
  | Readonly<{
      type: "evaluation_completed";
      judge: EvaluationJudge;
      groups: number;
      win: number;
      tie: number;
      loss: number;
      unresolved: number;
    }>
  | Readonly<{ type: "published"; model_id: string }>
  | Readonly<{ type: "cancel_requested"; requested_by: string }>
  | Readonly<{
      type: "run_finished";
      stage: TerminalStage;
      error_code?: "internal" | "attempt_deadline";
      message?: string;
    }>
  | Readonly<{
      type: "note";
      level: "info" | "warning" | "error";
      message: string;
    }>
  | Readonly<{
      type: "trainer_started";
      gpu: Gpu;
      image_digest: string;
      recipe: string;
    }>
  | Readonly<{
      type: "trainer_stage";
      stage:
        | "starting"
        | "preparing_data"
        | "training"
        | "checkpointing"
        | "uploading";
    }>
  | Readonly<{ type: "trainer_progress" } & RunProgress>
  | Readonly<{ type: "trainer_checkpoint"; step: number; sha256: string }>
  | Readonly<{
      type: "trainer_artifact_uploaded";
      name: string;
      sha256: string;
      size_bytes: number;
    }>
  | Readonly<{ type: "trainer_finished"; manifest_sha256: string }>
  | Readonly<{
      type: "trainer_failed";
      error_code:
        | "dataset_invalid"
        | "oom"
        | "judge_unavailable"
        | "upload_failed"
        | "deadline"
        | "internal";
      message: string;
    }>;

export type TrainingRunEvent = EventEnvelope & TrainingRunEventPayload;

export type RunProgress = Readonly<{
  step: number;
  total_steps: number;
  loss: number;
  mean_reward: number;
  tokens_per_second: number;
  eta_seconds: number;
}>;

export type TraceGenerationRow = Readonly<{
  id: string;
  trace_id: string;
  task: string;
  response_status: number;
  captured_at: string;
  model: string;
  latency_ms: number;
  input_tokens: number;
  output_tokens: number;
  cost_nano_usd: number;
}>;

export type ToolCall = Readonly<{ name: string; arguments: string }>;

export type AssistantReply =
  Readonly<{ content: string }> | Readonly<{ tool_call: ToolCall }>;

export type TraceMessage =
  | Readonly<{ role: "system"; content: string }>
  | Readonly<{ role: "user"; content: string }>
  | Readonly<{ role: "tool"; tool_name: string; content: string }>
  | (Readonly<{ role: "assistant"; generation_id: string }> & AssistantReply);

export type TaskStats = Readonly<{
  requests_7d: number;
  tokens_7d: number;
  usable_traces_since_last_run: number;
}>;

export type TraceSummary = Readonly<{
  trace_id: string;
  started_at: string;
  generation_count: number;
  duration_ms: number;
  cost_nano_usd: number;
  /** True when nothing grouped the generation, so `trace_id` is its generation id. */
  single_generation: boolean;
}>;

export type EvaluationResultLine = Readonly<{
  index: number;
  request_preview: string;
  comparison_response: string;
  fine_tuned_response: string;
  verdict: "better" | "equivalent" | "worse" | "unresolved";
}>;

export type VersionView = Readonly<{
  model: FineTunedModel;
  run: TrainingRunRow;
  summary: EvaluationSummary;
  is_production: boolean;
}>;
