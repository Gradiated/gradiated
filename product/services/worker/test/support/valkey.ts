import { execFile } from "node:child_process";
import { randomUUID } from "node:crypto";
import { promisify } from "node:util";

import { createValkeyClient, type RedisClientType } from "@gradiated/valkey";
import { inject } from "vitest";
import type { TestProject } from "vitest/node";

const IMAGE = "valkey/valkey:8.1.9-alpine3.24";
const LOCAL_HOSTS = new Set(["localhost", "127.0.0.1", "[::1]"]);
const READY_TIMEOUT_MS = 30_000;

declare module "vitest" {
  interface ProvidedContext {
    workerValkeyUrl: string;
  }
}

const execute = promisify(execFile);

// Containers must never land on a shared or remote Docker engine.
const localDockerHost = async (): Promise<string> => {
  const host =
    process.env.DOCKER_HOST ??
    (
      await execute("docker", [
        "context",
        "inspect",
        "--format",
        "{{.Endpoints.docker.Host}}",
      ])
    ).stdout.trim();

  if (!host.startsWith("unix://")) {
    throw new Error(`Refusing a non-local Docker endpoint: ${host}`);
  }

  return host;
};

const startContainer = async (): Promise<{
  url: string;
  close: () => Promise<void>;
}> => {
  const host = await localDockerHost().catch((error: unknown) => {
    throw new Error(
      "Worker tests need a local Docker engine or WORKER_TEST_VALKEY_URL.",
      { cause: error },
    );
  });
  const docker = async (...args: string[]): Promise<string> =>
    (await execute("docker", ["--host", host, ...args])).stdout.trim();
  const name = `worker-test-${randomUUID()}`;
  const remove = async () => {
    await docker("rm", "-f", "-v", name).catch(() => "");
  };

  try {
    await docker(
      "run",
      "-d",
      "--name",
      name,
      "--publish",
      "127.0.0.1::6379",
      IMAGE,
      "valkey-server",
      "--save",
      "",
      "--appendonly",
      "no",
    );

    const deadline = Date.now() + READY_TIMEOUT_MS;
    while (
      !(await docker("exec", name, "valkey-cli", "ping").catch(() => ""))
        .trim()
        .endsWith("PONG")
    ) {
      if (Date.now() >= deadline) {
        throw new Error("Valkey did not accept connections in time.");
      }

      await new Promise((resolve) => setTimeout(resolve, 100));
    }

    const published = await docker("port", name, "6379/tcp");
    const port = published.split("\n")[0]?.split(":").at(-1);
    if (!port) throw new Error(`Docker published no Valkey port: ${published}`);

    return { url: `redis://127.0.0.1:${port}`, close: remove };
  } catch (error) {
    await remove();
    throw error;
  }
};

export default async (project: TestProject) => {
  const url = process.env.WORKER_TEST_VALKEY_URL;

  if (url !== undefined) {
    if (!LOCAL_HOSTS.has(new URL(url).hostname)) {
      throw new Error("WORKER_TEST_VALKEY_URL must point at local Valkey.");
    }

    project.provide("workerValkeyUrl", url);
    return;
  }

  const server = await startContainer();
  project.provide("workerValkeyUrl", server.url);

  return server.close;
};

export const connectTestValkey = async (): Promise<RedisClientType> => {
  const client = createValkeyClient({ VALKEY_URL: inject("workerValkeyUrl") });
  await client.connect();

  return client;
};
