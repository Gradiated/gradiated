import type { components } from "@/api/schema";

type Schemas = components["schemas"];
export type TaskRow = Schemas["Task"];
export type TrainingRunRow = Schemas["TrainingRun"];
export type TrainingRunEvent = Schemas["TrainingRunEvent"];
export type TrainingRunEventPayload = Schemas["TrainingRunEventPayload"];
export type EvaluationSummary = NonNullable<Schemas["RunEvaluation"]>;
export type JudgeOutcome = EvaluationSummary["vs_comparison"];
export type EvaluationJudge = Schemas["EvaluationJudge"];
export type RunStage = Schemas["RunStage"];
export type RunProgress = Omit<
  Extract<TrainingRunEventPayload, { type: "trainer_progress" }>,
  "type"
>;
export type Gpu = Extract<
  TrainingRunEventPayload,
  { type: "capacity_granted" }
>["gpu"];
export type VersionView = Schemas["TaskVersion"] & {
  run: TrainingRunRow | undefined;
  summary: EvaluationSummary | null;
};

export { EVALUATION_JUDGES as EVALUATION_JUDGE_ALLOWLIST } from "@gradiated/contracts/model-catalog";

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
