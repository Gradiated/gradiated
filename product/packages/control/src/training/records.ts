import { z } from "zod";
import {
  TaskSchema,
  TaskVersionSchema,
  TrainingRunSchema,
  TrainingRunEventSchema,
  UuidSchema,
} from "@gradiated/contracts";

const timestamps = { createdAt: z.date(), updatedAt: z.date() };

export const TaskRecordSchema = z.object({
  id: TaskSchema.shape.id,
  workspaceId: UuidSchema,
  name: TaskSchema.shape.name,
  baseModelId: TaskSchema.shape.base_model_id,
  comparisonModelId: TaskSchema.shape.comparison_model_id,
  productionVersionId: TaskSchema.shape.production_version_id,
  trainingSchedule: TaskSchema.shape.training_schedule,
  ...timestamps,
});

export const RunRecordSchema = z.object({
  id: TrainingRunSchema.shape.id,
  taskId: UuidSchema,
  trigger: TrainingRunSchema.shape.trigger,
  requestedBy: TrainingRunSchema.shape.requested_by,
  stage: TrainingRunSchema.shape.stage,
  baseModelId: TrainingRunSchema.shape.base_model_id,
  inputCutoff: z.date(),
  dataset: TrainingRunSchema.shape.dataset,
  evaluation: TrainingRunSchema.shape.evaluation,
  cancelRequestedAt: z.date().nullable(),
  finishedAt: z.date().nullable(),
  ...timestamps,
});

export const VersionRecordSchema = z.object({
  id: TaskVersionSchema.shape.id,
  workspaceId: UuidSchema,
  taskId: UuidSchema,
  trainingRunId: TaskVersionSchema.shape.training_run_id,
  name: TaskVersionSchema.shape.name,
  baseModelId: TaskVersionSchema.shape.base_model_id,
  adapter: TaskVersionSchema.shape.adapter,
  status: TaskVersionSchema.shape.status,
  ...timestamps,
});

export const EventRecordSchema = z.object({
  id: TrainingRunEventSchema.shape.id,
  runId: UuidSchema,
  at: z.date(),
  source: TrainingRunEventSchema.shape.source,
  attempt: TrainingRunEventSchema.shape.attempt,
  payload: TrainingRunEventSchema.shape.payload,
});

export const RunInsertSchema = RunRecordSchema.pick({
  id: true,
  taskId: true,
  trigger: true,
  requestedBy: true,
  stage: true,
  baseModelId: true,
  inputCutoff: true,
});
export const RunUpdateSchema = RunRecordSchema.omit({
  id: true,
  taskId: true,
  createdAt: true,
}).partial();
export const RunResultFieldSchema = RunRecordSchema.pick({
  dataset: true,
  evaluation: true,
}).keyof();
export const VersionInsertSchema = VersionRecordSchema.omit({
  createdAt: true,
  updatedAt: true,
});
export const EventInsertSchema = EventRecordSchema.omit({ id: true });
export const TaskUpdateSchema = TaskRecordSchema.pick({
  baseModelId: true,
  comparisonModelId: true,
  productionVersionId: true,
  trainingSchedule: true,
  updatedAt: true,
}).partial();

export type TaskRecord = z.infer<typeof TaskRecordSchema>;
export type TaskVersionRecord = z.infer<typeof VersionRecordSchema>;
export type TrainingRunRecord = z.infer<typeof RunRecordSchema> & {
  task: string;
  versionId: string | null;
};
