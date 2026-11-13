import { z } from "@hono/zod-openapi";
import { ModelIdSchema } from "./common.js";

const money = z.number().int().nonnegative().max(Number.MAX_SAFE_INTEGER);
const positive = z.number().positive().finite();

export const WORKLOAD_BENCHMARK_FILE = "benchmark.json";
export const WorkloadBenchmarkSchema = z.strictObject({
  schema_version: z.literal(1),
  comparison_model_id: ModelIdSchema.nullable(),
  workload: z.string().trim().min(1).max(500),
  notes: z.string().max(4000),
  cost: z
    .strictObject({
      unit: z.enum(["task", "1k_tokens"]),
      fine_tuned: money,
      comparison: money.nullable(),
      basis: z.enum(["measured", "estimated"]),
    })
    .nullable(),
  speed: z
    .strictObject({
      unit: z.enum(["output_tokens_per_second", "latency_seconds"]),
      fine_tuned: positive,
      comparison: positive.nullable(),
      statistic: z.enum(["mean", "median"]),
    })
    .nullable(),
  quality: z
    .strictObject({
      metric: z.string().trim().min(1).max(200),
      fine_tuned: z.number().min(0).max(100),
      comparison: z.number().min(0).max(100).nullable(),
      sample_size: z.number().int().positive().nullable(),
    })
    .nullable(),
});
export type WorkloadBenchmark = z.infer<typeof WorkloadBenchmarkSchema>;
