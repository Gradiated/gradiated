import { createClient, type ClickHouseClient } from "@clickhouse/client";
import { createHash } from "node:crypto";
import { readdir, readFile } from "node:fs/promises";
import { z } from "zod";

const identifierPattern = /^[A-Za-z_][A-Za-z0-9_]*$/;

const environmentSchema = z.object({
  CLICKHOUSE_HOST: z.string().trim().min(1),
  CLICKHOUSE_PORT: z.coerce.number().int().min(1).max(65_535),
  CLICKHOUSE_SECURE: z
    .enum(["true", "false"])
    .transform((value) => value === "true"),
  CLICKHOUSE_DATABASE: z.string().regex(identifierPattern),
  CLICKHOUSE_ADMIN_USERNAME: z.string().min(1),
  CLICKHOUSE_ADMIN_PASSWORD: z.string().min(1),
  CLICKHOUSE_APPLICATION_USERNAME: z.string().regex(identifierPattern),
  CLICKHOUSE_APPLICATION_PASSWORD: z.string().min(1),
});

const safeIdentifier = (name: string, value: string): string => {
  if (!identifierPattern.test(value)) {
    throw new Error(`${name} must be a ClickHouse identifier`);
  }
  return `\`${value}\``;
};

const waitForClickHouse = async (client: ClickHouseClient): Promise<void> => {
  const deadline = Date.now() + 120_000;

  for (;;) {
    try {
      await client.command({ query: "SELECT 1" });
      return;
    } catch (error) {
      if (Date.now() >= deadline) throw error;
      await new Promise((resolve) => setTimeout(resolve, 1_000));
    }
  }
};

type Migration = {
  checksum: string;
  name: string;
  query: string;
};

type AppliedMigration = {
  checksum: string;
  name: string;
};

const loadMigrations = async (): Promise<Migration[]> => {
  const directory = new URL("../../clickhouse/migrations/", import.meta.url);
  const entries = await readdir(directory, { withFileTypes: true });
  const names = entries
    .filter(
      (entry) => entry.isFile() && /^\d{4}_[a-z0-9_]+\.sql$/.test(entry.name),
    )
    .map((entry) => entry.name)
    .sort();

  return Promise.all(
    names.map(async (name) => {
      const query = await readFile(new URL(name, directory), "utf8");
      return {
        checksum: createHash("sha256").update(query).digest("hex"),
        name,
        query,
      };
    }),
  );
};

const bootstrapDatabase = async (
  client: ClickHouseClient,
  database: string,
  adminUsername: string,
  applicationUsername: string,
  applicationPassword: string,
): Promise<void> => {
  const databaseIdentifier = safeIdentifier("CLICKHOUSE_DATABASE", database);
  const userIdentifier = safeIdentifier(
    "CLICKHOUSE_APPLICATION_USERNAME",
    applicationUsername,
  );

  await client.command({
    query: `CREATE DATABASE IF NOT EXISTS ${databaseIdentifier}`,
  });

  if (applicationUsername === adminUsername) return;

  await client.command({
    query: `CREATE USER IF NOT EXISTS ${userIdentifier} IDENTIFIED WITH sha256_password BY {application_password:String}`,
    query_params: { application_password: applicationPassword },
  });
  await client.command({
    query: `ALTER USER ${userIdentifier} IDENTIFIED WITH sha256_password BY {application_password:String}`,
    query_params: { application_password: applicationPassword },
  });
  await client.command({
    query: `GRANT SELECT, INSERT ON ${databaseIdentifier}.* TO ${userIdentifier}`,
  });
};

const ensureMigrationTable = async (
  client: ClickHouseClient,
): Promise<void> => {
  await client.command({
    query: `
      CREATE TABLE IF NOT EXISTS gradiated_schema_migrations
      (
        name String,
        checksum FixedString(64),
        applied_at DateTime64(6, 'UTC') DEFAULT now64(6)
      )
      ENGINE = MergeTree
      ORDER BY (name, applied_at)
    `,
  });
};

const getAppliedMigrations = async (
  client: ClickHouseClient,
): Promise<Map<string, string>> => {
  const result = await client.query({
    query: `
      SELECT name, argMax(checksum, applied_at) AS checksum
      FROM gradiated_schema_migrations
      GROUP BY name
      ORDER BY name
    `,
    format: "JSONEachRow",
  });
  const rows = await result.json<AppliedMigration>();
  return new Map(rows.map((row) => [row.name, row.checksum]));
};

const applyMigrations = async (client: ClickHouseClient): Promise<void> => {
  await ensureMigrationTable(client);
  const applied = await getAppliedMigrations(client);

  for (const migration of await loadMigrations()) {
    const currentChecksum = applied.get(migration.name);
    if (currentChecksum && currentChecksum !== migration.checksum) {
      throw new Error(`Applied migration changed: ${migration.name}`);
    }
    if (currentChecksum) continue;

    await client.command({ query: migration.query });
    await client.insert({
      table: "gradiated_schema_migrations",
      values: [{ name: migration.name, checksum: migration.checksum }],
      format: "JSONEachRow",
    });
    console.log(`Applied ClickHouse migration ${migration.name}`);
  }
};

const main = async (): Promise<void> => {
  const environment = environmentSchema.parse(process.env);
  const url = `${environment.CLICKHOUSE_SECURE ? "https" : "http"}://${environment.CLICKHOUSE_HOST}:${environment.CLICKHOUSE_PORT}`;

  const adminClient = createClient({
    url,
    username: environment.CLICKHOUSE_ADMIN_USERNAME,
    password: environment.CLICKHOUSE_ADMIN_PASSWORD,
    database: "default",
  });

  try {
    await waitForClickHouse(adminClient);
    await bootstrapDatabase(
      adminClient,
      environment.CLICKHOUSE_DATABASE,
      environment.CLICKHOUSE_ADMIN_USERNAME,
      environment.CLICKHOUSE_APPLICATION_USERNAME,
      environment.CLICKHOUSE_APPLICATION_PASSWORD,
    );

    const migrationClient = createClient({
      url,
      username: environment.CLICKHOUSE_ADMIN_USERNAME,
      password: environment.CLICKHOUSE_ADMIN_PASSWORD,
      database: environment.CLICKHOUSE_DATABASE,
    });
    try {
      await applyMigrations(migrationClient);
    } finally {
      await migrationClient.close();
    }
  } finally {
    await adminClient.close();
  }
};

await main();
