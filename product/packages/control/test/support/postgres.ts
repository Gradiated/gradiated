import { execFile } from "node:child_process";
import { randomUUID } from "node:crypto";
import { promisify } from "node:util";

import { drizzle } from "drizzle-orm/node-postgres";
import { migrate } from "drizzle-orm/node-postgres/migrator";
import { Client, Pool } from "pg";
import { inject } from "vitest";
import type { TestProject } from "vitest/node";

import {
  createControlDatabase,
  type ControlDatabaseClient,
} from "../../src/db/client.js";

const IMAGE = "postgres:17.10-alpine3.23";
const LOCAL_HOSTS = new Set(["localhost", "127.0.0.1", "[::1]"]);
const READY_TIMEOUT_MS = 30_000;

type ControlPostgres = { adminUrl: string; template: string };

declare module "vitest" {
  interface ProvidedContext {
    controlPostgres: ControlPostgres;
  }
}

const execute = promisify(execFile);

const dockerContextHost = async (): Promise<string> => {
  const { stdout } = await execute("docker", [
    "context",
    "inspect",
    "--format",
    "{{.Endpoints.docker.Host}}",
  ]);

  return stdout.trim();
};

// Containers must never land on a shared or remote Docker engine.
const localDockerHost = async (): Promise<string> => {
  const host = process.env.DOCKER_HOST ?? (await dockerContextHost());

  if (!host.startsWith("unix://")) {
    throw new Error(`Refusing a non-local Docker endpoint: ${host}`);
  }

  return host;
};

const createDocker = async () => {
  const host = await localDockerHost().catch((error: unknown) => {
    throw new Error(
      "Control tests need a local Docker engine or CONTROL_TEST_DATABASE_URL.",
      { cause: error },
    );
  });

  return async (...args: string[]): Promise<string> =>
    (await execute("docker", ["--host", host, ...args])).stdout.trim();
};

const withDatabase = (url: string, database: string): string => {
  const parsed = new URL(url);
  parsed.pathname = `/${database}`;

  return parsed.toString();
};

const runAdmin = async (adminUrl: string, statement: string) => {
  const client = new Client({ connectionString: adminUrl });
  await client.connect();

  try {
    await client.query(statement);
  } finally {
    await client.end();
  }
};

const waitUntilReady = async (ready: () => Promise<boolean>) => {
  const deadline = Date.now() + READY_TIMEOUT_MS;

  while (!(await ready().catch(() => false))) {
    if (Date.now() >= deadline) {
      throw new Error("PostgreSQL did not accept connections in time.");
    }

    await new Promise((resolve) => setTimeout(resolve, 100));
  }
};

type Server = { adminUrl: string; close: () => Promise<void> };

const startContainer = async (): Promise<Server> => {
  const docker = await createDocker();
  const name = `control-test-${randomUUID()}`;
  const remove = async () => {
    await docker("rm", "-f", "-v", name).catch(() => "");
  };

  try {
    await docker(
      "run",
      "-d",
      "--name",
      name,
      "--tmpfs",
      "/var/lib/postgresql/data:rw,nosuid,nodev,size=256m",
      "--publish",
      "127.0.0.1::5432",
      "-e",
      "POSTGRES_USER=control",
      "-e",
      "POSTGRES_PASSWORD=control",
      "-e",
      "POSTGRES_DB=control",
      IMAGE,
      "-c",
      "fsync=off",
    );

    // Readiness over TCP inside the container skips the init-only server,
    // which listens on the unix socket alone.
    await waitUntilReady(async () =>
      (
        await docker(
          "exec",
          name,
          "pg_isready",
          "--host",
          "127.0.0.1",
          "--username",
          "control",
          "--dbname",
          "control",
        )
      ).includes("accepting connections"),
    );

    const published = await docker("port", name, "5432/tcp");
    const port = published.split("\n")[0]?.split(":").at(-1);
    if (!port) {
      throw new Error(`Docker published no PostgreSQL port: ${published}`);
    }

    return {
      adminUrl: `postgres://control:control@127.0.0.1:${port}/control?sslmode=disable`,
      close: remove,
    };
  } catch (error) {
    await remove();
    throw error;
  }
};

const openServer = async (template: string): Promise<Server> => {
  const url = process.env.CONTROL_TEST_DATABASE_URL;
  if (url === undefined) return startContainer();

  if (!LOCAL_HOSTS.has(new URL(url).hostname)) {
    throw new Error(
      "CONTROL_TEST_DATABASE_URL must point at local PostgreSQL.",
    );
  }

  return {
    adminUrl: url,
    close: () =>
      runAdmin(url, `DROP DATABASE IF EXISTS "${template}" WITH (FORCE)`),
  };
};

const migrateTemplate = async (adminUrl: string, template: string) => {
  await runAdmin(adminUrl, `CREATE DATABASE "${template}"`);

  const pool = new Pool({
    connectionString: withDatabase(adminUrl, template),
  });

  try {
    await migrate(drizzle({ client: pool }), {
      migrationsFolder: new URL("../../migrations", import.meta.url).pathname,
    });
  } finally {
    await pool.end();
  }
};

export default async (project: TestProject) => {
  const template = `control_template_${randomUUID().replaceAll("-", "")}`;
  const server = await openServer(template);

  try {
    await migrateTemplate(server.adminUrl, template);
  } catch (error) {
    await server.close();
    throw error;
  }

  project.provide("controlPostgres", { adminUrl: server.adminUrl, template });

  return server.close;
};

export type TestDatabase = ControlDatabaseClient & {
  dispose: () => Promise<void>;
};

export const createTestDatabase = async (): Promise<TestDatabase> => {
  const { adminUrl, template } = inject("controlPostgres");
  const name = `control_test_${randomUUID().replaceAll("-", "")}`;

  await runAdmin(adminUrl, `CREATE DATABASE "${name}" TEMPLATE "${template}"`);

  const client = createControlDatabase(withDatabase(adminUrl, name));

  return {
    ...client,
    dispose: async () => {
      await client.pool.end();
      await runAdmin(
        adminUrl,
        `DROP DATABASE IF EXISTS "${name}" WITH (FORCE)`,
      );
    },
  };
};
