import { GenerationListQuerySchema, GenerationListSchema } from "./usage.js";
import {
  TaskGenerationQuerySchema,
  TraceGenerationListSchema,
} from "./traces.js";

import { z } from "@hono/zod-openapi";

import {
  CancellationOwnerSchema,
  GenerationStatusSchema,
  BoundedIdentifierSchema,
  TimestampSchema,
  TokenCountSchema,
  UuidSchema,
} from "./common.js";
import { ServiceTierSchema } from "./service-tiers.js";

export const GenerationPriceComponentSchema = z.strictObject({
  unit: z.enum([
    "request",
    "input_token",
    "cached_input_token",
    "cache_write_token",
    "output_token",
    "reasoning_token",
  ]),
  quantity: z.number().int().nonnegative(),
  unit_price: z.number().int().nonnegative(),
  amount: z.number().int().nonnegative(),
});

const generationPropertyFields = {
  estimated_joules: z.number().finite().nonnegative().nullable().optional(),
  external_id: z.string().max(300).nullable(),
  organization_id: UuidSchema,
  workspace_id: UuidSchema,
  api_key_id: UuidSchema,
  model_id: BoundedIdentifierSchema,
  served_release_digest: z.string().regex(/^sha256:[a-f0-9]{64}$/),
  status: GenerationStatusSchema,
  streamed: z.boolean(),
  pricing: z.strictObject({
    schema_version: z.literal(1),
    components: z.array(GenerationPriceComponentSchema),
  }),
  usage: z.strictObject({
    charge: z.number().int().nonnegative(),
    input_tokens: TokenCountSchema,
    cached_input_tokens: TokenCountSchema,
    cache_write_tokens: TokenCountSchema,
    output_tokens: TokenCountSchema,
    reasoning_tokens: TokenCountSchema,
  }),
  outcome: z.strictObject({
    finish_reason: z.string().max(100).nullable(),
    error_code: z.string().max(100).nullable(),
    usable_output_delivered: z.boolean(),
    cancellation_owner: CancellationOwnerSchema.nullable(),
  }),
  timing: z.strictObject({
    received_at: TimestampSchema,
    started_at: TimestampSchema.nullable(),
    first_token_at: TimestampSchema.nullable(),
    completed_at: TimestampSchema,
  }),
};

export const GenerationPropertiesSchema = z
  .discriminatedUnion("event_schema_version", [
    z.strictObject({
      ...generationPropertyFields,
      event_schema_version: z.literal(1),
    }),
    z.strictObject({
      ...generationPropertyFields,
      event_schema_version: z.literal(2),
      service_tier: ServiceTierSchema,
      lane: z
        .literal("eval")
        .optional()
        .describe("Set on grad's eval traffic, which bills like any other."),
      eval_id: z
        .string()
        .regex(/^[a-z]+_[A-Za-z0-9]{1,64}$/)
        .optional()
        .describe("The grad eval an eval-lane generation belongs to."),
    }),
  ])
  .openapi("GenerationProperties");

export const GenerationSettledSchema = z
  .strictObject({
    generation_id: UuidSchema,
    properties: GenerationPropertiesSchema,
  })
  .openapi("GenerationSettled");

export type GenerationProperties = z.infer<typeof GenerationPropertiesSchema>;
export type GenerationSettled = z.infer<typeof GenerationSettledSchema>;

export const GenerationsQuerySchema = z
  .strictObject({
    ...GenerationListQuerySchema.shape,
    from: GenerationListQuerySchema.shape.from
      .optional()
      .describe(
        "Start of the period, as an RFC 3339 timestamp. Required without task_id; periods are at most 93 days.",
      ),
    to: GenerationListQuerySchema.shape.to
      .optional()
      .describe(
        "End of the period, as an RFC 3339 timestamp. Required without task_id.",
      ),
    limit: z.coerce
      .number()
      .int()
      .min(1)
      .max(100)
      .optional()
      .describe("Generations per page; 25 by default."),
    sort: z
      .enum(["newest", "highest_cost"])
      .optional()
      .describe(
        "newest (the default) orders by received time; highest_cost by charge.",
      ),
    task_id: TaskGenerationQuerySchema.shape.task_id
      .optional()
      .describe(
        "Lists the generations captured for this task name instead, newest first, with each generation's content_ref. Takes only cursor, not the period or other filters.",
      ),
    cursor: z
      .string()
      .min(1)
      .max(4096)
      .optional()
      .describe("The next_cursor from the previous page; opaque."),
  })
  .superRefine((query, context) => {
    const result = (
      query.task_id === undefined
        ? GenerationListQuerySchema
        : TaskGenerationQuerySchema
    ).safeParse(query);
    if (!result.success)
      for (const issue of result.error.issues)
        context.addIssue({
          code: "custom",
          message: issue.message,
          path: issue.path,
        });
  });
export const GenerationsListSchema = z.union([
  TraceGenerationListSchema,
  GenerationListSchema,
]);
