import { z } from "@hono/zod-openapi";

import { TimestampSchema } from "./common.js";

export const ModelPricingEntrySchema = z
  .strictObject({
    unit: z.enum(["input_token", "output_token"]),
    cost: z.number().int().nonnegative(),
  })
  .openapi("ModelPricingEntry");

export const ModelCapacityEntrySchema = z
  .strictObject({
    metric: z.enum(["context_tokens", "max_output_tokens"]),
    value: z.number().int().positive(),
  })
  .openapi("ModelCapacityEntry");

export const ModelParameterDescriptorSchema = z
  .strictObject({
    type: z.enum(["boolean", "integer", "number", "string"]),
    minimum: z.number().optional(),
    maximum: z.number().optional(),
  })
  .openapi("ModelParameterDescriptor");

export const ModelPropertiesSchema = z
  .strictObject({
    schema_version: z.number().int().positive(),
    description: z.string().max(2_000),
    released_at: TimestampSchema.nullable(),
    hugging_face_id: z.string().max(300).nullable(),
    quantization: z.string().max(100).nullable(),
    tokenizer: z.string().max(100).nullable(),
    input_modalities: z
      .array(z.strictObject({ type: z.literal("text") }))
      .min(1),
    output_modalities: z
      .array(z.strictObject({ type: z.literal("text") }))
      .min(1),
    pricing: z.array(ModelPricingEntrySchema).min(1),
    capacity: z.array(ModelCapacityEntrySchema).min(1),
    passthrough_parameters: z.record(
      z.string().min(1).max(100),
      ModelParameterDescriptorSchema,
    ),
    deprecation_at: TimestampSchema.nullable(),
    is_free: z.boolean(),
    discount_to_user: z.number().min(0).lt(1),
    openrouter: z.strictObject({ slug: z.string().min(1).max(300) }).nullable(),
  })
  .openapi("ModelProperties");

export const ModelSchema = z
  .strictObject({
    id: z.string().min(1).max(200),
    name: z.string().min(1).max(200),
    status: z.enum(["available", "unavailable"]),
    properties: ModelPropertiesSchema,
    created_at: TimestampSchema,
    updated_at: TimestampSchema,
  })
  .openapi("Model");

export const ModelListSchema = z
  .strictObject({
    data: z.array(ModelSchema),
    next_cursor: z.string().nullable(),
  })
  .openapi("ModelList");

export type Model = z.infer<typeof ModelSchema>;
export type ModelProperties = z.infer<typeof ModelPropertiesSchema>;
