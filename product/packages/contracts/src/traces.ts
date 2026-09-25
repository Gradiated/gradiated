import { z } from "@hono/zod-openapi";
import { TimestampSchema, UuidSchema } from "./common.js";
import { WorkspacePathSchema } from "./workspaces.js";

export const TaskGenerationQuerySchema = z.strictObject({
  task_id: z
    .string()
    .min(1)
    .max(256)
    .describe("Exact task identifier supplied in the capture header."),
  cursor: z
    .string()
    .max(4096)
    .optional()
    .describe("Opaque continuation for captured generations."),
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
  generation_id: UuidSchema,
});
export const TraceContentQuerySchema = z.object({
  content_ref: z.string().min(1).max(2048),
});
export const TraceContentSchema = z
  .object({
    generation_id: UuidSchema,
    raw: z.record(z.string(), z.unknown()).nullable(),
    canonical: z.unknown().nullable(),
  })
  .openapi("TraceContent");
export type TraceGeneration = z.infer<typeof TraceGenerationSchema>;
