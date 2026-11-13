import { z } from "@hono/zod-openapi";

import {
  CancellationOwnerSchema,
  GenerationStatusSchema,
  BoundedIdentifierSchema,
  pageFields,
  TimestampSchema,
  TokenCountSchema,
  UnsignedIntegerStringSchema,
  UuidSchema,
} from "./common.js";

const DateRangeFields = {
  from: TimestampSchema,
  to: TimestampSchema,
};

const MAX_RANGE_MILLISECONDS = 93 * 24 * 60 * 60 * 1_000;

const validateDateRange = (
  value: { from: string; to: string },
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

const UsageTotalsFields = {
  charge: UnsignedIntegerStringSchema,
  input_tokens: UnsignedIntegerStringSchema,
  output_tokens: UnsignedIntegerStringSchema,
  generation_count: UnsignedIntegerStringSchema,
};

export const UsagePointSchema = z.object({
  date: z.iso.date(),
  ...UsageTotalsFields,
});

export const UsageModelBreakdownSchema = z.object({
  model_id: BoundedIdentifierSchema,
  ...UsageTotalsFields,
});

export const UsageSummarySchema = z.object({
  ...UsageTotalsFields,
  succeeded_count: UnsignedIntegerStringSchema,
  daily: z.array(UsagePointSchema),
  models: z.array(UsageModelBreakdownSchema),
});

export const GenerationListQuerySchema = z
  .object({
    ...DateRangeFields,
    cursor: z.string().min(1).max(1_000).optional(),
    limit: z.coerce.number().int().min(1).max(100).default(25),
    api_key_id: UuidSchema.optional(),
    model: BoundedIdentifierSchema.optional(),
    search: z.string().trim().min(1).max(300).optional(),
    sort: z.enum(["newest", "highest_cost"]).default("newest"),
    status: GenerationStatusSchema.optional(),
  })
  .strict()
  .superRefine(validateDateRange);

export const GenerationLogSchema = z.object({
  estimated_joules: z.number().finite().nonnegative().nullable().optional(),
  id: UuidSchema,
  external_id: z.string().nullable(),
  model_id: BoundedIdentifierSchema,
  status: GenerationStatusSchema,
  streamed: z.boolean(),
  charge: UnsignedIntegerStringSchema,
  input_tokens: TokenCountSchema,
  cached_input_tokens: TokenCountSchema,
  cache_write_tokens: TokenCountSchema,
  output_tokens: TokenCountSchema,
  reasoning_tokens: TokenCountSchema,
  finish_reason: z.string().nullable(),
  error_code: z.string().nullable(),
  usable_output_delivered: z.boolean(),
  cancellation_owner: CancellationOwnerSchema.nullable(),
  received_at: TimestampSchema,
  started_at: TimestampSchema.nullable(),
  first_token_at: TimestampSchema.nullable(),
  completed_at: TimestampSchema,
});

export const GenerationListSchema = z.object(pageFields(GenerationLogSchema));

export type GenerationList = z.infer<typeof GenerationListSchema>;
export type GenerationLog = z.infer<typeof GenerationLogSchema>;
export type UsageSummary = z.infer<typeof UsageSummarySchema>;
