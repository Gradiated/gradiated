import { readFile, readdir } from "node:fs/promises";
import { createClient } from "@clickhouse/client";
import type { TestProject } from "vitest/node";

import { LocalDocker } from "../../../gateway/test/integration/stack/docker.js";
import { eventually } from "../../../gateway/test/integration/eventually.js";
import { freePort } from "../../../gateway/test/integration/ports.js";

declare module "vitest" {
  interface ProvidedContext {
    workerClickHouseUrl: string;
  }
}

export default async (project: TestProject) => {
  const docker = await LocalDocker.connect(
    `worker-clickhouse-${crypto.randomUUID()}`,
  );
  const port = await freePort();
  const url = `http://127.0.0.1:${port}`;
  const client = createClient({
    url,
    username: "test",
    password: "test",
    database: "test",
  });

  try {
    await docker.run("clickhouse", [
      "--publish",
      `127.0.0.1:${port}:8123`,
      "-e",
      "CLICKHOUSE_DB=test",
      "-e",
      "CLICKHOUSE_USER=test",
      "-e",
      "CLICKHOUSE_PASSWORD=test",
      "-e",
      "CLICKHOUSE_DEFAULT_ACCESS_MANAGEMENT=1",
      "clickhouse/clickhouse-server:26.7.1-alpine",
    ]);
    await eventually(
      async () => (await fetch(`${url}/ping`)).ok,
      30_000,
      "ClickHouse readiness",
    );
    const directory = new URL(
      "../../../../packages/control/clickhouse/migrations/",
      import.meta.url,
    );
    for (const name of (await readdir(directory))
      .filter((name) => name.endsWith(".sql"))
      .sort()) {
      await client.command({
        query: await readFile(new URL(name, directory), "utf8"),
      });
    }
    project.provide("workerClickHouseUrl", url);
  } catch (error) {
    await docker.removeOwned();
    throw error;
  } finally {
    await client.close();
  }

  return () => docker.removeOwned();
};
