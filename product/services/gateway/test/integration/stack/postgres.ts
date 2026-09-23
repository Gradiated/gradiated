import { spawn } from "node:child_process";
import { join } from "node:path";

import { eventually } from "../eventually.js";
import { freePort } from "../ports.js";
import type { LocalDocker } from "./docker.js";

const IMAGE = "postgres:17.10-alpine3.23";
const PRODUCT_ROOT = join(import.meta.dirname, "../../../../..");

/** Its own PostgreSQL on a random port; never a developer's database. */
export const startPostgres = async (docker: LocalDocker): Promise<string> => {
  const port = await freePort();
  const container = await docker.run("postgres", [
    "--network",
    "host",
    "--tmpfs",
    "/var/lib/postgresql/data:rw,nosuid,nodev,size=256m",
    "-e",
    "POSTGRES_USER=gradiated",
    "-e",
    "POSTGRES_PASSWORD=gradiated",
    "-e",
    "POSTGRES_DB=gradiated",
    IMAGE,
    "-c",
    `port=${port}`,
    "-c",
    "listen_addresses=127.0.0.1",
    "-c",
    "fsync=off",
  ]);

  await eventually(
    async () =>
      (
        await docker.output(
          "exec",
          container,
          "pg_isready",
          "--username",
          "gradiated",
          "--dbname",
          "gradiated",
          "--port",
          String(port),
        )
      ).includes("accepting connections"),
    30_000,
    "postgres did not accept connections",
  );

  const databaseUrl = `postgres://gradiated:gradiated@127.0.0.1:${port}/gradiated?sslmode=disable`;
  await migrate(databaseUrl);

  return databaseUrl;
};

// The product's own migrations, so this schema cannot drift from the one the
// gateway's queries are written against.
const migrate = (databaseUrl: string): Promise<void> =>
  new Promise((resolve, reject) => {
    const migration = spawn(
      "pnpm",
      ["--filter", "@gradiated/control", "db:migrate"],
      {
        cwd: PRODUCT_ROOT,
        env: { ...process.env, DATABASE_URL: databaseUrl },
        stdio: "ignore",
      },
    );

    migration.once("error", reject);
    migration.once("exit", (code) =>
      code === 0
        ? resolve()
        : reject(new Error(`control migrations exited with ${String(code)}`)),
    );
  });
