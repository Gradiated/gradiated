import { z } from "zod";
import {
  EvaluationJudgeSchema,
  TaskSchema,
  TrainingRunSchema,
  UuidSchema,
} from "@gradiated/contracts";

export const TrainingInputSchema = z.object({
  taskId: UuidSchema,
  workspaceId: UuidSchema,
  name: TaskSchema.shape.name,
  baseModelId: TrainingRunSchema.shape.base_model_id,
  comparisonModelId: TaskSchema.shape.comparison_model_id.unwrap(),
  judgeModelId: EvaluationJudgeSchema,
  inputCutoff: TrainingRunSchema.shape.input_cutoff,
  trigger: TrainingRunSchema.shape.trigger,
  requestedBy: TrainingRunSchema.shape.requested_by,
});
export type TrainingInput = z.infer<typeof TrainingInputSchema>;

export interface TrainingEngine {
  start(input: TrainingInput): Promise<string>;
  status(
    workflowId: string,
    runId: string,
  ): Promise<"running" | "succeeded" | "failed" | "cancelled">;
  cancel(taskId: string, runId: string, workflowId?: string): Promise<void>;
  updateSchedule(taskId: string, cron: string | null): Promise<void>;
}

export class TrainingAdmissionError extends Error {
  constructor(
    readonly code:
      "already_training" | "insufficient_traces" | "training_not_configured",
    message: string,
  ) {
    super(message);
    this.name = "TrainingAdmissionError";
  }
}
