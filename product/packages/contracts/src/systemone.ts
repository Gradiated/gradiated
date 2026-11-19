import { z } from "@hono/zod-openapi";

import { ModelIdSchema, NameSchema, TokenCountSchema } from "./common.js";

// kev/api.py JSONContent: recursive JSON, including scalar/null descriptions.
export const SystemOneJsonSchema = z
  .json()
  .describe(
    "JSON content, including nested objects/arrays, finite numbers, booleans and null. The runtime additionally enforces body, nesting-depth and token bounds (currently 1 MiB, 32 levels and 8192 input tokens).",
  )
  .openapi("SystemOneJson", {
    // Explicit metadata stops the OpenAPI generator from expanding z.json() recursively.
    type: ["string", "number", "boolean", "object", "array", "null"],
    additionalProperties: {},
    items: {},
  });

const LevelIndexSchema = z.string().regex(/^(0|[1-9]\d*)$/);
const HostedModelIdSchema = ModelIdSchema.describe(
  "Exact hosted model ID, required; no default, alias resolution or fallback.",
);
const InstructionsSchema = SystemOneJsonSchema.optional().describe(
  "Question instructions as JSON. Optional, as in TypeSafe's API: the TypeSafe SDK omits them when a question has only criteria.",
);

const boundedMap = <T extends z.ZodType>(
  key: z.ZodString,
  value: T,
  { min, max }: { min: number; max: number },
) =>
  z
    .record(key, value)
    .refine((map) => {
      const size = Object.keys(map).length;

      return size >= min && size <= max;
    }, `Expected ${min}..${max} entries`)
    .openapi({ minProperties: min, maxProperties: max });

export const SystemOneQuestionSchema = z
  .discriminatedUnion("type", [
    z.strictObject({
      type: z.literal("choice").describe("Select one named option."),
      instructions: InstructionsSchema,
      criteria: boundedMap(z.string(), SystemOneJsonSchema, {
        min: 1,
        max: 255,
      }).describe(
        "One to 255 named options with JSON descriptions; null leaves an option undescribed.",
      ),
    }),
    z.strictObject({
      type: z.literal("noul").describe("Estimate the probability of true."),
      instructions: InstructionsSchema,
      criteria: z
        .strictObject({
          false: SystemOneJsonSchema.optional().describe(
            "Description of the false outcome.",
          ),
          true: SystemOneJsonSchema.optional().describe(
            "Description of the true outcome.",
          ),
        })
        .nullable()
        .optional()
        .describe(
          "Optional JSON descriptions for false and true outcomes. Other keys are rejected to prevent silently ignored options.",
        ),
    }),
    z.strictObject({
      type: z
        .literal("score")
        .describe("Expected zero-based level on an ordered rubric."),
      instructions: InstructionsSchema,
      criteria: z
        .array(SystemOneJsonSchema)
        .min(1)
        .max(255)
        .describe(
          "One to 255 ordered JSON level descriptions, indexed from zero. A single level is answered with certainty.",
        ),
    }),
  ])
  .describe("A native Kev choice, noul or score question.")
  .openapi("SystemOneQuestion");

export const SystemOneRequestSchema = z
  .strictObject({
    model: HostedModelIdSchema,
    state: z
      .union([
        z.string(),
        z.record(z.string(), SystemOneJsonSchema),
        z.array(SystemOneJsonSchema),
      ])
      .describe(
        "State to evaluate: text, a JSON object or an array. Nested JSON scalars are allowed.",
      ),
    questions: boundedMap(NameSchema, SystemOneQuestionSchema, {
      min: 1,
      max: 64,
    }).describe("One to 64 named questions; each name is 1..200 characters."),
    session_id: z
      .string()
      .min(1)
      .max(256)
      .optional()
      .describe(
        "Optional session affinity identifier, at most 256 characters.",
      ),
    service_tier: z
      .literal("default")
      .default("default")
      .describe(
        "Only default is implemented for SystemOne; fast and flex are rejected.",
      ),
  })
  .describe(
    "POST /v1/systemone. Non-streaming inference only; output-token controls and unknown fields are rejected.",
  )
  .openapi("SystemOneRequest");

const ProbabilitySchema = z
  .number()
  .min(0)
  .max(1)
  .describe("Probability or confidence in [0, 1].");
const ProbabilitiesSchema = boundedMap(z.string(), ProbabilitySchema, {
  min: 1,
  max: 255,
}).describe(
  "Per-option probabilities, rounded independently by Kev; their sum need not be exactly one.",
);

export const SystemOneAnswerSchema = z
  .discriminatedUnion("type", [
    z.strictObject({
      type: z
        .literal("choice")
        .describe("Answer selecting one of the named options."),
      choice: z.string().describe("Selected option name."),
      confidence: ProbabilitySchema,
      probabilities: ProbabilitiesSchema,
    }),
    z.strictObject({
      type: z
        .literal("noul")
        .describe("Answer reporting the probability of true."),
      noul: ProbabilitySchema.describe("Probability that the answer is true."),
    }),
    z.strictObject({
      type: z
        .literal("score")
        .describe("Answer scoring the state against the ordered rubric."),
      score: z
        .number()
        .min(0)
        .max(254)
        .describe("Expected zero-based rubric level, potentially fractional."),
      confidence: ProbabilitySchema,
      legend: boundedMap(LevelIndexSchema, z.string(), {
        min: 1,
        max: 255,
      }).describe(
        "Zero-based level indices mapped to rendered upstream JSON descriptions.",
      ),
      probabilities: boundedMap(LevelIndexSchema, ProbabilitySchema, {
        min: 1,
        max: 255,
      }).describe("Probabilities keyed by zero-based level index."),
    }),
  ])
  .describe("Native inference answer, keyed by the original question name.")
  .openapi("SystemOneAnswer");

export const SystemOneUsageSchema = z
  .strictObject({
    input_tokens: TokenCountSchema.describe(
      "Total input tokens, including cached input.",
    ),
    cached_input_tokens: TokenCountSchema.describe(
      "Cached subset of input_tokens.",
    ),
    output_tokens: z
      .literal(0)
      .describe("Always zero: pointer inference generates no output tokens."),
  })
  .refine((usage) => usage.cached_input_tokens <= usage.input_tokens, {
    message: "Cached input cannot exceed total input tokens",
    path: ["cached_input_tokens"],
  })
  .describe(
    "Native inference token usage; serialized answers are not generated tokens.",
  )
  .openapi("SystemOneUsage");

export const SystemOneResponseSchema = z
  .strictObject({
    model: HostedModelIdSchema,
    answers: boundedMap(NameSchema, SystemOneAnswerSchema, {
      min: 1,
      max: 64,
    }).describe("Answers keyed by the request question names."),
    usage: SystemOneUsageSchema,
    latency_ms: z
      .number()
      .nonnegative()
      .optional()
      .describe("Optional inference latency in milliseconds."),
  })
  .describe("Completed native SystemOne inference response.")
  .openapi("SystemOneResponse");

export type SystemOneQuestion = z.infer<typeof SystemOneQuestionSchema>;
export type SystemOneRequest = z.infer<typeof SystemOneRequestSchema>;
export type SystemOneAnswer = z.infer<typeof SystemOneAnswerSchema>;
export type SystemOneUsage = z.infer<typeof SystemOneUsageSchema>;
export type SystemOneResponse = z.infer<typeof SystemOneResponseSchema>;
