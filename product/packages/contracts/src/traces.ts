import { z } from "@hono/zod-openapi";
import { TimestampSchema, UuidSchema } from "./common.js";
import { WorkspacePathSchema } from "./workspaces.js";

export const TaskGenerationQuerySchema = z.strictObject({
  task_id: z
    .string()
    .min(1)
    .max(256)
    .describe(
      "The task's name, exactly as sent in the capture header. Content is stored only for generations captured for a task.",
    ),
  cursor: z
    .string()
    .max(4096)
    .optional()
    .describe("The next_cursor from the previous page; opaque."),
});
export const TraceGenerationSchema = z
  .object({
    generation_id: UuidSchema,
    trace_id: z.string(),
    task: z.string(),
    model: z.string(),
    source: z.enum(["relay", "hosted", "import"]),
    trainable: z.boolean(),
    started_at: TimestampSchema,
    completed_at: TimestampSchema.nullable(),
    status: z.number().int().nullable(),
    outcome: z.string().nullable(),
    usage: z.record(z.string(), z.unknown()).nullable(),
    content_ref: z
      .string()
      .describe("Opaque reference for fetching this generation's content."),
  })
  .openapi("TraceGeneration");
export const TraceGenerationListSchema = z
  .object({
    data: z.array(TraceGenerationSchema),
    next_cursor: z.string().nullable(),
  })
  .openapi("TraceGenerationList");
export const TraceContentPathSchema = WorkspacePathSchema.extend({
  generation_id: UuidSchema.describe("The generation's ID."),
});
export const TraceContentQuerySchema = z
  .object({
    content_ref: z
      .string()
      .min(1)
      .max(2048)
      .optional()
      .describe(
        "The content_ref returned with the generation when listing a task's generations. Locates the content directly.",
      ),
    task_id: TaskGenerationQuerySchema.shape.task_id.optional(),
  })
  .refine(
    (query) =>
      (query.content_ref === undefined) !== (query.task_id === undefined),
    "Provide content_ref or task_id.",
  );
export const TraceContentSchema = z
  .object({
    generation_id: UuidSchema,
    raw: z.record(z.string(), z.unknown()).nullable(),
    canonical: z.unknown().nullable(),
  })
  .openapi("TraceContent");
export type TraceGeneration = z.infer<typeof TraceGenerationSchema>;
