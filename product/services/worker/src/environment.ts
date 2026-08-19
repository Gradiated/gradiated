import { clickHouseRuntimeEnvironmentSchema } from "@gradiated/control";
import { z } from "zod";

const environmentSchema = clickHouseRuntimeEnvironmentSchema.extend({
  DATABASE_URL: z.url(),
  VALKEY_URL: z.url(),
  VALKEY_IAM_CACHE_NAME: z.string().trim().min(1).optional(),
  VALKEY_IAM_REGION: z.string().trim().min(1).optional(),
  VALKEY_IAM_USER: z.string().trim().min(1).optional(),
  GENERATION_STREAM_KEY: z
    .string()
    .min(1)
    .default("generation-settled:{settlement-0}"),
  GENERATION_CONSUMER_GROUP: z
    .string()
    .min(1)
    .default("clickhouse-generation-ingest-v1"),
  WORKER_CONSUMER_NAME: z.string().min(1),
  GENERATION_BATCH_SIZE: z.coerce.number().int().min(1).max(1_000).default(100),
  GENERATION_READ_BLOCK_MS: z.coerce
    .number()
    .int()
    .min(100)
    .max(60_000)
    .default(5_000),
  GENERATION_CLAIM_IDLE_MS: z.coerce
    .number()
    .int()
    .min(1_000)
    .max(3_600_000)
    .default(30_000),
  SETTLEMENT_DELAY_SECONDS: z.coerce
    .number()
    .int()
    .min(300)
    .max(86_400)
    .default(600),
  SETTLEMENT_MAX_SLOTS_PER_PASS: z.coerce
    .number()
    .int()
    .min(1)
    .max(1_000)
    .default(100),
  SETTLEMENT_POLL_SECONDS: z.coerce.number().int().min(1).max(300).default(10),
  PROJECTOR_BALANCE_TRANSACTION_BATCH_SIZE: z.coerce
    .number()
    .int()
    .min(1)
    .max(10_000)
    .default(500),
  PROJECTOR_POLL_SECONDS: z.coerce
    .number()
    .int()
    .min(1)
    .max(3_600)
    .default(30),
});

export type WorkerEnvironment = z.infer<typeof environmentSchema>;

export const parseWorkerEnvironment = (
  environment: NodeJS.ProcessEnv,
): WorkerEnvironment => environmentSchema.parse(environment);
