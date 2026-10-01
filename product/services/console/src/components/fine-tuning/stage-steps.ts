import {
  STAGE_ORDER,
  isTerminalStage,
  type RunStage,
} from "@/store/fine-tuning-types";

export type StepState =
  "done" | "current" | "failed" | "cancelled" | "skipped" | "pending";

export const isStopped = (stage: RunStage) =>
  stage === "failed" || stage === "cancelled" || stage === "cancelling";

export const stepState = (
  stage: RunStage,
  runStage: RunStage,
  visited: readonly RunStage[],
): StepState => {
  if (stage === runStage) {
    if (stage === "failed") return "failed";
    if (stage === "cancelled") return "cancelled";
    if (!isTerminalStage(stage)) return "current";
  }

  const lastActiveStage = visited.findLast(
    (entry) => !isTerminalStage(entry) && entry !== "cancelling",
  );
  if (
    stage === lastActiveStage &&
    (runStage === "failed" || runStage === "cancelled")
  )
    return runStage;

  if (visited.includes(stage)) return "done";

  return isStopped(runStage) ? "skipped" : "pending";
};

export const stepsFor = (
  runStage: RunStage,
  visited: readonly RunStage[],
): readonly RunStage[] => {
  if (!isStopped(runStage)) return STAGE_ORDER;

  const unfinished = STAGE_ORDER.filter(
    (stage): stage is Exclude<typeof stage, "succeeded"> =>
      stage !== "succeeded",
  );

  return [
    ...unfinished.filter((stage) => visited.includes(stage)),
    runStage,
    ...unfinished.filter((stage) => !visited.includes(stage)),
  ];
};

export const initiallyOpenStage = (runStage: RunStage): RunStage | null => {
  if (!isTerminalStage(runStage)) return runStage;

  return isStopped(runStage) ? runStage : null;
};
