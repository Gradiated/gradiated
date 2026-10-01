import { z } from "zod";

const environmentSchema = z.object({
  DATABASE_URL: z.url(),
  CONTENTS_BUCKET: z.string().min(1),
  TRAINING_EXECUTOR: z.enum(["mock", "qwen-sft"]),
  PORT: z.coerce.number().int().min(1).max(65_535).default(3005),
  METRICS_PORT: z.coerce.number().int().min(1).max(65_535).default(9464),
});

export const parseTemporalWorkerEnvironment = (
  environment: NodeJS.ProcessEnv,
) => environmentSchema.parse(environment);
