import { z } from "@hono/zod-openapi";

import {
  ModelIdSchema,
  NameSchema,
  pageFields,
  TimestampSchema,
} from "./common.js";
import { MODEL_USE_CASES } from "./model-catalog.js";
import {
  ServiceTierPricingPolicySchema,
  ServiceTierSchema,
} from "./service-tiers.js";

const DEFAULT_OUTPUT_TOKENS = 1_024;

const TokenMeasureSchema = z.strictObject({
  value: z.number().int().positive(),
  unit: z.literal("token"),
});

const orderedBounds = [
  ({ min, max }: { min: number; max: number }) => min <= max,
  { message: "min cannot exceed max" },
] as const;

const RangeParameterDescriptorSchema = z
  .strictObject({
    type: z.literal("range"),
    min: z.number(),
    max: z.number(),
  })
  .refine(...orderedBounds);

const IntegerParameterDescriptorSchema = z
  .strictObject({
    type: z.literal("integer"),
    min: z.number().int(),
    max: z.number().int(),
    unit: z.literal("token").optional(),
  })
  .refine(...orderedBounds);

const EnumParameterValueSchema = z.union([z.string(), z.number(), z.boolean()]);

export const ModelParameterDescriptorSchema = z
  .discriminatedUnion("type", [
    RangeParameterDescriptorSchema,
    IntegerParameterDescriptorSchema,
    z.strictObject({ type: z.literal("boolean") }),
    z.strictObject({
      type: z.literal("enum"),
      values: z.array(EnumParameterValueSchema).min(1),
    }),
    z.strictObject({ type: z.literal("unknown") }),
  ])
  .openapi("ModelParameterDescriptor");

const ParameterMapSchema = z.record(
  z.string().min(1).max(100),
  ModelParameterDescriptorSchema,
);

const InputTokenPricingEntrySchema = z.strictObject({
  type: z.enum(["prompt", "cached_prompt", "cache_write"]),
  unit: z.literal("token"),
  cost: z.number().int().nonnegative(),
});

const OutputTokenPricingEntrySchema = z.strictObject({
  type: z.enum(["completion", "internal_reasoning"]),
  unit: z.literal("token"),
  cost: z.number().int().nonnegative(),
});

export const ModelPricingEntrySchema = z
  .union([InputTokenPricingEntrySchema, OutputTokenPricingEntrySchema])
  .openapi("ModelPricingEntry");

const uniquePricingTypes = (
  entries: ReadonlyArray<{ type: string }>,
): boolean => new Set(entries.map(({ type }) => type)).size === entries.length;

const sortByPricingType = <Entry extends { type: string }>(
  entries: ReadonlyArray<Entry>,
  order: ReadonlyArray<Entry["type"]>,
): Entry[] =>
  [...entries].sort((a, b) => order.indexOf(a.type) - order.indexOf(b.type));

const TextInputModalitySchema = z
  .strictObject({
    type: z.literal("text"),
    supported_inputs: z.strictObject({
      max_context_length: TokenMeasureSchema,
      max_prompt_length: TokenMeasureSchema,
    }),
    pricing: z
      .array(InputTokenPricingEntrySchema)
      .min(2)
      .max(3)
      .refine(uniquePricingTypes, { message: "pricing types must be unique" })
      .refine(
        (entries) =>
          entries.some(({ type }) => type === "prompt") &&
          entries.some(({ type }) => type === "cached_prompt"),
        { message: "prompt and cached_prompt pricing are required" },
      ),
  })
  .refine(
    ({ supported_inputs }) =>
      supported_inputs.max_prompt_length.value <=
      supported_inputs.max_context_length.value,
    { message: "max_prompt_length cannot exceed max_context_length" },
  );

const TextInputModalityInputSchema = z
  .strictObject({
    type: z.literal("text"),
    supported_inputs: z.strictObject({
      max_context_length: TokenMeasureSchema,
      max_prompt_length: TokenMeasureSchema.optional(),
    }),
    pricing: z.array(InputTokenPricingEntrySchema),
  })
  .transform((modality) => {
    const prompt = modality.pricing.find(({ type }) => type === "prompt");
    const hasCachedPrompt = modality.pricing.some(
      ({ type }) => type === "cached_prompt",
    );
    const pricing =
      prompt && !hasCachedPrompt
        ? [
            ...modality.pricing,
            {
              type: "cached_prompt" as const,
              unit: "token" as const,
              cost: prompt.cost,
            },
          ]
        : modality.pricing;

    return {
      ...modality,
      supported_inputs: {
        ...modality.supported_inputs,
        max_prompt_length:
          modality.supported_inputs.max_prompt_length ??
          modality.supported_inputs.max_context_length,
      },
      pricing: sortByPricingType(
        pricing,
        InputTokenPricingEntrySchema.shape.type.options,
      ),
    };
  })
  .pipe(TextInputModalitySchema);

const TextOutputModalitySchema = z
  .strictObject({
    type: z.literal("text"),
    max_length: TokenMeasureSchema,
    default_length: TokenMeasureSchema,
    streaming: z.boolean(),
    supported_parameters: ParameterMapSchema,
    pricing: z
      .array(OutputTokenPricingEntrySchema)
      .min(1)
      .max(2)
      .refine(uniquePricingTypes, { message: "pricing types must be unique" })
      .refine((entries) => entries.some(({ type }) => type === "completion"), {
        message: "completion pricing is required",
      }),
  })
  .refine(
    ({ default_length, max_length }) =>
      default_length.value <= max_length.value,
    { message: "default_length cannot exceed max_length" },
  )
  .refine(
    ({ pricing, supported_parameters }) =>
      !Object.hasOwn(supported_parameters, "reasoning") ||
      pricing.some(({ type }) => type === "internal_reasoning"),
    {
      message:
        "internal_reasoning pricing is required when reasoning is supported",
    },
  );

const TextOutputModalityInputSchema = z
  .strictObject({
    type: z.literal("text"),
    max_length: TokenMeasureSchema,
    default_length: TokenMeasureSchema.optional(),
    streaming: z.boolean().default(true),
    supported_parameters: ParameterMapSchema.default({}),
    pricing: z.array(OutputTokenPricingEntrySchema),
  })
  .transform((modality) => {
    const completion = modality.pricing.find(
      ({ type }) => type === "completion",
    );
    const needsReasoningPrice =
      Object.hasOwn(modality.supported_parameters, "reasoning") &&
      !modality.pricing.some(({ type }) => type === "internal_reasoning");
    const pricing =
      completion && needsReasoningPrice
        ? [
            ...modality.pricing,
            {
              type: "internal_reasoning" as const,
              unit: "token" as const,
              cost: completion.cost,
            },
          ]
        : modality.pricing;

    return {
      ...modality,
      default_length: modality.default_length ?? {
        value: Math.min(DEFAULT_OUTPUT_TOKENS, modality.max_length.value),
        unit: "token" as const,
      },
      pricing: sortByPricingType(
        pricing,
        OutputTokenPricingEntrySchema.shape.type.options,
      ),
    };
  })
  .pipe(TextOutputModalitySchema);

const QuantizationSchema = z.enum([
  "int4",
  "int8",
  "fp4",
  "mxfp4",
  "nvfp4",
  "fp6",
  "fp8",
  "mxfp8",
  "fp16",
  "bf16",
  "fp32",
]);

const ModelTypeSchema = z
  .enum(["chat", "decision"])
  .describe(
    "The inference interface: chat generates text; decision scores typed questions without generating text.",
  );

const ModelSupportedUsesSchema = z
  .array(z.enum(MODEL_USE_CASES))
  .describe(
    "Product uses: serving is available for inference; training, judge and comparison are internal workflow uses.",
  );

// Field names and shapes follow OpenRouter's model list (`default_parameters`,
// `reasoning`), so catalog clients can read either source the same way.
const DefaultParametersSchema = z
  .strictObject({
    temperature: z.number().nullable().optional(),
    top_p: z.number().nullable().optional(),
    top_k: z.number().int().nullable().optional(),
    frequency_penalty: z.number().nullable().optional(),
    presence_penalty: z.number().nullable().optional(),
    repetition_penalty: z.number().nullable().optional(),
  })
  .describe(
    "Sampling values the runtime applies when a request omits them; null or absent means not published.",
  )
  .openapi("ModelDefaultParameters");

const ReasoningEffortSchema = z.string().min(1).max(32);

const ModelReasoningSchema = z
  .strictObject({
    supported_efforts: z
      .array(ReasoningEffortSchema)
      .min(1)
      .describe("reasoning_effort values the model accepts, lowest first."),
    default_effort: ReasoningEffortSchema.nullable().describe(
      "Effort applied when a request omits reasoning_effort.",
    ),
  })
  .refine(
    ({ supported_efforts, default_effort }) =>
      default_effort === null || supported_efforts.includes(default_effort),
    { message: "default_effort must be a supported effort" },
  )
  .describe("Reasoning effort levels; absent for models without them.")
  .openapi("ModelReasoning");

const parameterDescriptor = (
  properties: {
    output_modalities: ReadonlyArray<{
      supported_parameters: Record<string, ModelParameterDescriptor>;
    }>;
  },
  name: string,
) => properties.output_modalities[0]?.supported_parameters[name];

const DEFAULT_PARAMETER_NAMES = [
  "temperature",
  "top_p",
  "top_k",
  "frequency_penalty",
  "presence_penalty",
  "repetition_penalty",
] as const;

const BaseModelPropertiesSchema = z.strictObject({
  schema_version: z.literal(1),
  description: z.string().max(2_000),
  released_at: TimestampSchema.nullable(),
  hugging_face_id: z.string().max(300).nullable(),
  quantization: QuantizationSchema.nullable(),
  tokenizer: z.string().max(100).nullable(),
  input_modalities: z.array(TextInputModalitySchema).length(1),
  output_modalities: z.array(TextOutputModalitySchema).length(1),
  passthrough_parameters: ParameterMapSchema,
  default_parameters: DefaultParametersSchema.optional(),
  reasoning: ModelReasoningSchema.optional(),
  deprecation_date: TimestampSchema.nullable(),
  pricing_overrides: z
    .array(
      z.strictObject({
        min_prompt_tokens: z
          .number()
          .int()
          .nonnegative()
          .describe("Minimum total input tokens for this price tier."),
        input_pricing: z
          .array(InputTokenPricingEntrySchema)
          .describe(
            "Input rates overriding the base tier, in nano-USD per token.",
          ),
        output_pricing: z
          .array(OutputTokenPricingEntrySchema)
          .describe(
            "Output rates overriding the base tier, in nano-USD per token.",
          ),
      }),
    )
    .optional()
    .describe(
      "Published long-context price overrides; unspecified token types inherit base rates.",
    ),
});

// Defaults and efforts must describe parameters the model accepts, within their bounds.
export const ModelPropertiesSchema = BaseModelPropertiesSchema.superRefine(
  (properties, context) => {
    for (const name of DEFAULT_PARAMETER_NAMES) {
      const value = properties.default_parameters?.[name];
      if (value === undefined || value === null) continue;

      const descriptor = parameterDescriptor(properties, name);
      const outOfBounds =
        (descriptor?.type === "range" || descriptor?.type === "integer") &&
        (value < descriptor.min || value > descriptor.max);

      if (!descriptor || outOfBounds) {
        context.addIssue({
          code: "custom",
          path: ["default_parameters", name],
          message: descriptor
            ? `${name} default is outside the supported range`
            : `${name} has a default but is not a supported parameter`,
        });
      }
    }

    if (!properties.reasoning) return;

    const effort = parameterDescriptor(properties, "reasoning_effort");
    const undeclared =
      effort?.type === "enum"
        ? properties.reasoning.supported_efforts.filter(
            (level) => !effort.values.includes(level),
          )
        : [];

    if (!effort || undeclared.length) {
      context.addIssue({
        code: "custom",
        path: ["reasoning", "supported_efforts"],
        message: effort
          ? `reasoning_effort does not accept ${undeclared.join(", ")}`
          : "reasoning requires the reasoning_effort parameter",
      });
    }
  },
);

export const ModelPropertiesInputSchema = z
  .strictObject({
    schema_version: z.literal(1).default(1),
    description: z.string().max(2_000),
    released_at: TimestampSchema.nullable().default(null),
    hugging_face_id: z.string().max(300).nullable().default(null),
    quantization: QuantizationSchema.nullable().default(null),
    tokenizer: z.string().max(100).nullable().default(null),
    input_modalities: z.array(TextInputModalityInputSchema).length(1),
    output_modalities: z.array(TextOutputModalityInputSchema).length(1),
    passthrough_parameters: ParameterMapSchema.default({}),
    default_parameters: DefaultParametersSchema.optional(),
    reasoning: ModelReasoningSchema.optional(),
    deprecation_date: TimestampSchema.nullable().default(null),
  })
  .pipe(ModelPropertiesSchema);

const CatalogModelSchema = z.strictObject({
  id: ModelIdSchema,
  name: NameSchema,
  status: z.enum(["available", "unavailable"]),
  properties: ModelPropertiesSchema,
  icon: z
    .string()
    .nullable()
    .optional()
    .describe("Provider icon path in the console's local assets."),
  created_at: TimestampSchema,
  updated_at: TimestampSchema,
});

export const ModelSchema = CatalogModelSchema.extend({
  properties: BaseModelPropertiesSchema.extend({
    type: ModelTypeSchema,
    supported_uses: ModelSupportedUsesSchema,
  }).openapi("ModelProperties"),
}).openapi("Model");

export const ExternalModelSchema = CatalogModelSchema.extend({
  properties: BaseModelPropertiesSchema.extend({
    type: ModelTypeSchema.optional(),
  }).openapi("ExternalModelProperties"),
}).openapi("ExternalModel");

const CatalogModelListSchema = z.strictObject({
  ...pageFields(ModelSchema),
  service_tiers: z
    .array(ServiceTierPricingPolicySchema)
    .length(ServiceTierSchema.options.length),
  pricing_source: z
    .literal("openrouter")
    .optional()
    .describe(
      "External pricing source; rates are catalog estimates, not billing charges.",
    ),
  pricing_updated_at: TimestampSchema.optional().describe(
    "Time this API instance fetched the external catalog.",
  ),
});

export const ModelListSchema = CatalogModelListSchema.openapi("ModelList");
export const ExternalModelListSchema = CatalogModelListSchema.extend({
  data: z.array(ExternalModelSchema),
}).openapi("ExternalModelList");

export type Model = z.infer<typeof ModelSchema>;
export type ExternalModel = z.infer<typeof ExternalModelSchema>;
export type ModelParameterDescriptor = z.infer<
  typeof ModelParameterDescriptorSchema
>;
export type ModelPricingEntry = z.infer<typeof ModelPricingEntrySchema>;
export type ModelProperties = z.infer<typeof ModelPropertiesSchema>;
export type ModelPropertiesInput = z.input<typeof ModelPropertiesInputSchema>;
