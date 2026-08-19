import { createClient, type ClickHouseClient } from "@clickhouse/client";
import { z } from "zod";

export const clickHouseRuntimeEnvironmentSchema = z.object({
  CLICKHOUSE_DATABASE: z.string().trim().min(1),
  CLICKHOUSE_HOST: z.string().trim().min(1),
  CLICKHOUSE_PASSWORD: z.string().min(1),
  CLICKHOUSE_PORT: z.coerce.number().int().min(1).max(65_535),
  CLICKHOUSE_SECURE: z
    .enum(["true", "false"])
    .transform((value) => value === "true"),
  CLICKHOUSE_USERNAME: z.string().trim().min(1),
});

export type ClickHouseRuntimeEnvironment = z.infer<
  typeof clickHouseRuntimeEnvironmentSchema
>;

export const parseClickHouseRuntimeEnvironment = (
  environment: NodeJS.ProcessEnv,
): ClickHouseRuntimeEnvironment =>
  clickHouseRuntimeEnvironmentSchema.parse(environment);

export const createClickHouseRuntimeClient = (
  environment: ClickHouseRuntimeEnvironment,
): ClickHouseClient =>
  createClient({
    url: `${environment.CLICKHOUSE_SECURE ? "https" : "http"}://${environment.CLICKHOUSE_HOST}:${environment.CLICKHOUSE_PORT}`,
    username: environment.CLICKHOUSE_USERNAME,
    password: environment.CLICKHOUSE_PASSWORD,
    database: environment.CLICKHOUSE_DATABASE,
  });
