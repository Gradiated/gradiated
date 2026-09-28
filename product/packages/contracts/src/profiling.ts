import { z } from "@hono/zod-openapi";

import {
  BoundedIdentifierSchema,
  DeploymentIdSchema,
  ModelIdSchema,
  TimestampSchema,
  UuidSchema,
} from "./common.js";

export const ProfilingEventSchema = z.strictObject({
  id: UuidSchema,
  observed_at: TimestampSchema,
  event_type: z
    .string()
    .min(1)
    .max(120)
    .regex(/^[a-z][a-z0-9_.-]*$/),
  properties: z.record(z.string().min(1).max(200), z.unknown()),
});

export const ProfilingEventBatchSchema = z.strictObject({
  schema_version: z.literal(1),
  batch_id: UuidSchema,
  deployment_id: DeploymentIdSchema,
  model_id: ModelIdSchema,
  runtime_revision: BoundedIdentifierSchema,
  events: z.array(ProfilingEventSchema).min(1).max(1_000),
});

export type ProfilingEvent = z.infer<typeof ProfilingEventSchema>;
export type ProfilingEventBatch = z.infer<typeof ProfilingEventBatchSchema>;
