import { z } from "@hono/zod-openapi";
import { TimestampSchema } from "./common.js";

const CountSchema = z.number().int().nonnegative();
const MessageSchema = z.object({
  role: z.enum(["system", "user", "assistant"]),
  content: z.string().min(1),
});

export const SftExampleSchema = z.object({
  prompt: z.array(MessageSchema).min(1),
  completion: z
    .array(MessageSchema.extend({ role: z.literal("assistant") }))
    .length(1),
  id: z.string().optional(),
  group: z.string().optional(),
});

const DatasetFileSchema = z.object({
  uri: z.string().min(1),
  sha256: z.string().regex(/^[0-9a-f]{64}$/),
  size_bytes: CountSchema,
});
const DatasetSplitSchema = z.object({
  examples: CountSchema,
  files: z.array(DatasetFileSchema).min(1),
});

export const SftDatasetManifestSchema = z.object({
  schema_version: z.literal(1),
  format: z.literal("conversational_prompt_completion"),
  encoding: z.literal("jsonl"),
  splits: z.object({
    train: DatasetSplitSchema,
    validation: DatasetSplitSchema,
    test: DatasetSplitSchema,
  }),
  evaluation_sample: DatasetSplitSchema.extend({
    source_split: z.literal("test"),
    selection: z.literal("first_by_example_id"),
    max_examples: z.number().int().positive(),
  }).optional(),
  builder: z.object({
    id: z.string().min(1),
    version: z.number().int().positive(),
    split: z.object({
      algorithm: z.literal("sha256_group_modulo_10"),
      group_by: z.literal("session_and_shared_prompt"),
      buckets: z.object({
        train: z.array(z.number().int().min(0).max(9)),
        validation: z.array(z.number().int().min(0).max(9)),
        test: z.array(z.number().int().min(0).max(9)),
      }),
    }),
    max_examples: z.number().int().positive(),
    max_content_bytes: z.number().int().positive(),
  }),
  provenance: z
    .object({
      input_cutoff: TimestampSchema,
      oldest_trace_at: TimestampSchema,
      newest_trace_at: TimestampSchema,
    })
    .optional(),
});
export type SftDatasetManifest = z.infer<typeof SftDatasetManifestSchema>;
