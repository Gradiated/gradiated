import { createClient, type ClickHouseClient } from "@clickhouse/client";
import { createHash } from "node:crypto";
import { readdir, readFile } from "node:fs/promises";
import { z } from "zod";

import { clickHouseServerEnvironmentSchema, clickHouseUrl } from "./client.js";
import {
  identifierPattern,
  pendingMigrations,
  safeIdentifier,
  selectMigrationFiles,
  type Migration,
} from "./migrations.js";

const environmentSchema = clickHouseServerEnvironmentSchema.extend({
  CLICKHOUSE_DATABASE: z.string().regex(identifierPattern),
  CLICKHOUSE_ADMIN_USERNAME: z.string().min(1),
  CLICKHOUSE_ADMIN_PASSWORD: z.string().min(1),
  CLICKHOUSE_APPLICATION_USERNAME: z.string().regex(identifierPattern),
  CLICKHOUSE_APPLICATION_PASSWORD: z.string().min(1),
  CLICKHOUSE_METABASE_USERNAME: z.string().regex(identifierPattern),
  CLICKHOUSE_METABASE_PASSWORD: z.string().min(1),
});

const appliedMigrationSchema = z.object({
  checksum: z.string(),
  name: z.string(),
});

type Credentials = { username: string; password: string };

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

const loadMigrations = async (): Promise<Migration[]> => {
  const directory = new URL("../../clickhouse/migrations/", import.meta.url);
  const entries = await readdir(directory, { withFileTypes: true });
  const names = selectMigrationFiles(
    entries.filter((entry) => entry.isFile()).map((entry) => entry.name),
  );

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

const ensureUser = async (
  client: ClickHouseClient,
  user: Credentials & {
    database: string;
    grant: "SELECT, INSERT" | "SELECT";
    variable: string;
  },
): Promise<void> => {
  const userIdentifier = safeIdentifier(user.variable, user.username);
  const identified = `IDENTIFIED WITH sha256_password BY {password:String}`;
  const queryParams = { password: user.password };

  await client.command({
    query: `CREATE USER IF NOT EXISTS ${userIdentifier} ${identified}`,
    query_params: queryParams,
  });
  await client.command({
    query: `ALTER USER ${userIdentifier} ${identified}`,
    query_params: queryParams,
  });
  await client.command({
    query: `GRANT ${user.grant} ON ${user.database}.* TO ${userIdentifier}`,
  });
};

const bootstrapDatabase = async (
  client: ClickHouseClient,
  options: {
    database: string;
    adminUsername: string;
    application: Credentials;
    metabase: Credentials;
  },
): Promise<void> => {
  const database = safeIdentifier("CLICKHOUSE_DATABASE", options.database);

  await client.command({ query: `CREATE DATABASE IF NOT EXISTS ${database}` });

  if (options.application.username !== options.adminUsername) {
    await ensureUser(client, {
      ...options.application,
      database,
      grant: "SELECT, INSERT",
      variable: "CLICKHOUSE_APPLICATION_USERNAME",
    });
  }

  await ensureUser(client, {
    ...options.metabase,
    database,
    grant: "SELECT",
    variable: "CLICKHOUSE_METABASE_USERNAME",
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
  const rows = appliedMigrationSchema.array().parse(await result.json());

  return new Map(rows.map((row) => [row.name, row.checksum]));
};

const applyMigrations = async (client: ClickHouseClient): Promise<void> => {
  await ensureMigrationTable(client);

  const pending = pendingMigrations(
    await loadMigrations(),
    await getAppliedMigrations(client),
  );

  for (const migration of pending) {
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
  const url = clickHouseUrl(environment);
  const admin = {
    url,
    username: environment.CLICKHOUSE_ADMIN_USERNAME,
    password: environment.CLICKHOUSE_ADMIN_PASSWORD,
  };

  const adminClient = createClient({ ...admin, database: "default" });

  try {
    await waitForClickHouse(adminClient);
    await bootstrapDatabase(adminClient, {
      database: environment.CLICKHOUSE_DATABASE,
      adminUsername: environment.CLICKHOUSE_ADMIN_USERNAME,
      application: {
        username: environment.CLICKHOUSE_APPLICATION_USERNAME,
        password: environment.CLICKHOUSE_APPLICATION_PASSWORD,
      },
      metabase: {
        username: environment.CLICKHOUSE_METABASE_USERNAME,
        password: environment.CLICKHOUSE_METABASE_PASSWORD,
      },
    });

    const migrationClient = createClient({
      ...admin,
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
