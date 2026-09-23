import { createClient, type ClickHouseClient } from "@clickhouse/client";
import { z } from "zod";

export const clickHouseServerEnvironmentSchema = z.object({
  CLICKHOUSE_HOST: z.string().trim().min(1),
  CLICKHOUSE_PORT: z.coerce.number().int().min(1).max(65_535),
  CLICKHOUSE_SECURE: z
    .enum(["true", "false"])
    .transform((value) => value === "true"),
});

export const clickHouseRuntimeEnvironmentSchema =
  clickHouseServerEnvironmentSchema.extend({
    CLICKHOUSE_DATABASE: z.string().trim().min(1),
    CLICKHOUSE_PASSWORD: z.string().min(1),
    CLICKHOUSE_USERNAME: z.string().trim().min(1),
  });

export type ClickHouseRuntimeEnvironment = z.infer<
  typeof clickHouseRuntimeEnvironmentSchema
>;

export const parseClickHouseRuntimeEnvironment = (
  environment: NodeJS.ProcessEnv,
): ClickHouseRuntimeEnvironment =>
  clickHouseRuntimeEnvironmentSchema.parse(environment);

// ClickHouse JSON output quotes UInt64 values unless
// output_format_json_quote_64bit_integers is off, so both forms arrive.
export const clickHouseUInt64Schema = z.union([
  z.string().regex(/^\d+$/),
  z.number().int().nonnegative(),
]);

export const clickHouseUrl = (
  server: z.infer<typeof clickHouseServerEnvironmentSchema>,
): string =>
  `${server.CLICKHOUSE_SECURE ? "https" : "http"}://${server.CLICKHOUSE_HOST}:${server.CLICKHOUSE_PORT}`;

export const createClickHouseRuntimeClient = (
  environment: ClickHouseRuntimeEnvironment,
): ClickHouseClient =>
  createClient({
    url: clickHouseUrl(environment),
    username: environment.CLICKHOUSE_USERNAME,
    password: environment.CLICKHOUSE_PASSWORD,
    database: environment.CLICKHOUSE_DATABASE,
  });

export const insertDeduplicated = async (
  client: Pick<ClickHouseClient, "insert">,
  insert: { table: string; values: unknown[]; token: string },
): Promise<void> => {
  const result = await client.insert({
    table: insert.table,
    columns: ["id", "properties"],
    values: insert.values,
    format: "JSONEachRow",
    clickhouse_settings: {
      async_insert: 1,
      async_insert_deduplicate: 1,
      insert_deduplication_token: insert.token,
      wait_for_async_insert: 1,
    },
  });

  if (!result.executed) {
    throw new Error(
      `ClickHouse did not execute the ${insert.table} insert ${insert.token}`,
    );
  }
};
