export const RUN_STAGE_ORDER = [
  "queued",
  "building_dataset",
  "awaiting_capacity",
  "training",
  "verifying",
  "publishing",
  "evaluating",
] as const;

export const TERMINAL_RUN_STAGES = [
  "succeeded",
  "failed",
  "cancelled",
] as const;

export const RUN_STAGES = [
  ...RUN_STAGE_ORDER,
  "cancelling",
  ...TERMINAL_RUN_STAGES,
] as const;

export type RunStage = (typeof RUN_STAGES)[number];
export type TerminalRunStage = (typeof TERMINAL_RUN_STAGES)[number];

export const isTerminalRunStage = (
  stage: RunStage,
): stage is TerminalRunStage =>
  TERMINAL_RUN_STAGES.some((terminal) => terminal === stage);
