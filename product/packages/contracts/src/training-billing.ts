import { z } from "@hono/zod-openapi";

import { TimestampSchema, UuidSchema } from "./common.js";

// grad (the training platform) calls these on the API's private training listener.

export const PriceVersionSchema = z
  .string()
  .regex(/^pv_[a-z0-9_]{1,60}$/)
  .describe("An immutable price-list version.")
  .openapi({ example: "pv_training_2026_11_27_placeholder" });

export const TrainingSkuSchema = z
  .string()
  .max(220)
  .regex(/^train:[a-z0-9][a-z0-9._-]*\/[a-z0-9][a-z0-9._-]*$/)
  .describe("train:<base model>, priced per million tokens.")
  .openapi({ example: "train:qwen/qwen3-8b" });

export const PriceSkuSchema = z
  .string()
  .max(220)
  .regex(/^(train|inference):[a-z0-9][a-z0-9._-]*\/[a-z0-9][a-z0-9._-]*$/)
  .describe(
    "train:<base model> is billed through usage ingest; inference:<gateway model> is a blended prompt and completion price grad uses only to estimate evals and to allow judges.",
  )
  .openapi({ example: "inference:anthropic/claude-sonnet-5-5" });

const NanoUsdSchema = z
  .union([
    z.number().int().nonnegative().max(Number.MAX_SAFE_INTEGER),
    z.string().regex(/^\d{1,19}$/),
  ])
  .transform((value) => BigInt(value))
  .refine((value) => value <= 9_223_372_036_854_775_807n, "Out of range.");

export const PriceListQuerySchema = z.object({
  product: z.literal("training"),
  price_version: PriceVersionSchema.optional().describe(
    "Return this version instead of the current one.",
  ),
});

export const PriceListSchema = z
  .strictObject({
    price_version: PriceVersionSchema,
    product: z.literal("training"),
    effective_at: TimestampSchema,
    placeholder: z
      .boolean()
      .describe("True while the prices are made up and not final."),
    skus: z.array(
      z.strictObject({
        sku: PriceSkuSchema,
        unit: z.literal("token"),
        price_nano_usd_per_mtok: z.number().int().nonnegative(),
      }),
    ),
  })
  .openapi("TrainingPriceList");

export const UsageEventSchema = z.strictObject({
  event_id: z
    .string()
    .min(1)
    .max(300)
    .regex(/^training:[A-Za-z0-9:._/-]+$/)
    .describe("Globally unique; replays with the same ID are free."),
  workspace_id: UuidSchema,
  product: z.literal("training"),
  sku: TrainingSkuSchema,
  quantity: z.number().int().nonnegative().max(Number.MAX_SAFE_INTEGER),
  amount_nano_usd: NanoUsdSchema,
  price_version: PriceVersionSchema,
  occurred_at: TimestampSchema,
  subject_id: z.string().min(1).max(200),
  tags: z
    .record(
      z
        .string()
        .min(1)
        .max(64)
        .regex(/^[a-z][a-z0-9_]*$/),
      z.string().max(200),
    )
    .refine((tags) => Object.keys(tags).length <= 32, "At most 32 tags.")
    .default({}),
});

export const UsageEventBatchSchema = z
  .strictObject({ events: z.array(UsageEventSchema).min(1).max(500) })
  .openapi("TrainingUsageEventBatch");

export const UsageEventIngestResultSchema = z
  .strictObject({
    accepted: z.number().int().nonnegative(),
    duplicates: z.number().int().nonnegative(),
  })
  .openapi("TrainingUsageEventIngestResult");

export const UsageEventRejectionCodes = [
  "price_mismatch",
  "unknown_workspace",
  "event_conflict",
] as const;

export const UsageEventRejectionSchema = z
  .strictObject({
    code: z.enum(UsageEventRejectionCodes),
    event_id: z.string(),
    message: z.string(),
  })
  .openapi("TrainingUsageEventRejection");

export const BalanceCheckSchema = z
  .strictObject({
    workspace_id: UuidSchema,
    estimated_amount_nano_usd: NanoUsdSchema.optional(),
    estimated_cost_usd: z.number().nonnegative().max(1e9).optional(),
  })
  .refine(
    (input) =>
      (input.estimated_amount_nano_usd === undefined) !==
      (input.estimated_cost_usd === undefined),
    "Send exactly one of estimated_amount_nano_usd and estimated_cost_usd.",
  )
  .openapi("TrainingBalanceCheck");

export const BalanceCheckResultSchema = z
  .strictObject({
    allowed: z.boolean(),
    reason: z.enum(["insufficient_balance", "suspended"]).optional(),
  })
  .openapi("TrainingBalanceCheckResult");

export type PriceList = z.infer<typeof PriceListSchema>;
export type UsageEvent = z.infer<typeof UsageEventSchema>;
export type UsageEventBatch = z.infer<typeof UsageEventBatchSchema>;
export type UsageEventRejectionCode = (typeof UsageEventRejectionCodes)[number];
export type BalanceCheck = z.infer<typeof BalanceCheckSchema>;
export type BalanceCheckResult = z.infer<typeof BalanceCheckResultSchema>;
