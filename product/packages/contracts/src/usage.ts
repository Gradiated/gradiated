import { z } from "@hono/zod-openapi";

import { TimestampSchema, UuidSchema } from "./common.js";

const DateRangeFields = {
  from: TimestampSchema,
  to: TimestampSchema,
};

const MAX_RANGE_MILLISECONDS = 93 * 24 * 60 * 60 * 1_000;

const validateDateRange = <T extends { from: string; to: string }>(
  value: T,
  context: z.RefinementCtx,
) => {
  const from = new Date(value.from).getTime();
  const to = new Date(value.to).getTime();
  if (from >= to) {
    context.addIssue({
      code: "custom",
      message: "The end time must be after the start time.",
      path: ["to"],
    });
  } else if (to - from > MAX_RANGE_MILLISECONDS) {
    context.addIssue({
      code: "custom",
      message: "The date range cannot exceed 93 days.",
      path: ["to"],
    });
  }
};

export const UsageQuerySchema = z
  .object(DateRangeFields)
  .superRefine(validateDateRange);

export const UsagePointSchema = z.object({
  date: z.iso.date(),
  charge: z.string().regex(/^\d+$/),
  input_tokens: z.string().regex(/^\d+$/),
  output_tokens: z.string().regex(/^\d+$/),
  generation_count: z.string().regex(/^\d+$/),
});

export const UsageModelBreakdownSchema = z.object({
  model_id: z.string().min(1).max(200),
  charge: z.string().regex(/^\d+$/),
  input_tokens: z.string().regex(/^\d+$/),
  output_tokens: z.string().regex(/^\d+$/),
  generation_count: z.string().regex(/^\d+$/),
});

export const UsageSummarySchema = z.object({
  charge: z.string().regex(/^\d+$/),
  input_tokens: z.string().regex(/^\d+$/),
  output_tokens: z.string().regex(/^\d+$/),
  generation_count: z.string().regex(/^\d+$/),
  succeeded_count: z.string().regex(/^\d+$/),
  daily: z.array(UsagePointSchema),
  models: z.array(UsageModelBreakdownSchema),
});

export const GenerationListQuerySchema = z
  .object({
    ...DateRangeFields,
    cursor: z.string().min(1).max(1_000).optional(),
    limit: z.coerce.number().int().min(1).max(100).default(25),
    api_key_id: UuidSchema.optional(),
    model: z.string().min(1).max(200).optional(),
    search: z.string().trim().min(1).max(300).optional(),
    sort: z.enum(["newest", "highest_cost"]).default("newest"),
    status: z
      .enum(["succeeded", "failed", "cancelled", "abandoned"])
      .optional(),
  })
  .superRefine(validateDateRange);

export const GenerationLogSchema = z.object({
  id: UuidSchema,
  external_id: z.string().nullable(),
  model_id: z.string().min(1).max(200),
  status: z.enum(["succeeded", "failed", "cancelled", "abandoned"]),
  streamed: z.boolean(),
  charge: z.string().regex(/^\d+$/),
  input_tokens: z.number().int().nonnegative(),
  cached_input_tokens: z.number().int().nonnegative(),
  cache_write_tokens: z.number().int().nonnegative(),
  output_tokens: z.number().int().nonnegative(),
  reasoning_tokens: z.number().int().nonnegative(),
  finish_reason: z.string().nullable(),
  error_code: z.string().nullable(),
  usable_output_delivered: z.boolean(),
  cancellation_owner: z.enum(["client", "server", "runtime"]).nullable(),
  received_at: TimestampSchema,
  started_at: TimestampSchema.nullable(),
  first_token_at: TimestampSchema.nullable(),
  completed_at: TimestampSchema,
});

export const GenerationListSchema = z.object({
  data: z.array(GenerationLogSchema),
  next_cursor: z.string().nullable(),
});

export type GenerationList = z.infer<typeof GenerationListSchema>;
export type GenerationLog = z.infer<typeof GenerationLogSchema>;
export type UsageSummary = z.infer<typeof UsageSummarySchema>;
