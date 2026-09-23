import { existsSync } from "node:fs";
import { mkdir, rm } from "node:fs/promises";

import type { TestProject } from "vitest/node";

import {
  BINARY,
  GATEWAY_LOG_DIR,
  GatewayProcess,
  GENERATION_TIMEOUT_SECONDS,
} from "./gateway-process.js";
import { isRuntimeKind, type RuntimeKind } from "./mock-runtimes/server.js";
import { freePort } from "./ports.js";
import { LocalDocker } from "./stack/docker.js";
import { startPostgres } from "./stack/postgres.js";
import { startRealRuntime, type RealRuntimes } from "./stack/real-runtimes.js";
import { startValkey } from "./stack/valkey.js";

export interface Stack {
  readonly redisUrl: string;
  readonly databaseUrl: string;
  readonly gatewayUrl: string;
  /**
   * A gateway whose generation deadline is patient enough for real CPU inference.
   * The shared one runs a short deadline so cancellation tests are quick.
   */
  readonly patientGatewayUrl: string | null;
  readonly runtimeToken: string;
}

const PATIENT_GENERATION_TIMEOUT_SECONDS = 120;

declare module "vitest" {
  interface ProvidedContext {
    stack: Stack;
    realRuntimes: RealRuntimes;
  }
}

/** GATEWAY_REAL_RUNTIME names the real runtimes to start, such as "vllm,kev". */
const enabledRealRuntimes = (): RuntimeKind[] =>
  (process.env.GATEWAY_REAL_RUNTIME ?? "")
    .split(",")
    .map((name) => name.trim())
    .filter((name) => name !== "")
    .map((name) => {
      if (!isRuntimeKind(name)) {
        throw new Error(`Unknown real runtime "${name}"; expected vllm or kev`);
      }

      return name;
    });

export default async (project: TestProject) => {
  if (!existsSync(BINARY)) {
    throw new Error(
      `Build the gateway binary before running integration tests: ${BINARY}`,
    );
  }

  const enabled = enabledRealRuntimes();
  const owner = `gateway-contract-${crypto.randomUUID().replaceAll("-", "")}`;
  const docker = await LocalDocker.connect(owner);
  const runtimeToken = crypto.randomUUID().replaceAll("-", "");
  const gateways: GatewayProcess[] = [];

  await rm(GATEWAY_LOG_DIR, { recursive: true, force: true });
  await mkdir(GATEWAY_LOG_DIR, { recursive: true });

  const teardown = async () => {
    await Promise.all(gateways.map((gateway) => gateway.stop()));
    await docker.removeOwned();
    console.info(`gateway logs: ${GATEWAY_LOG_DIR}`);
  };

  try {
    const databaseUrl = await startPostgres(docker);
    const redisUrl = await startValkey(docker);

    const startGateway = async (
      logName: string,
      generationTimeoutSeconds: number,
    ): Promise<string> => {
      const gateway = await GatewayProcess.start({
        redisUrl,
        databaseUrl,
        runtimeToken,
        port: await freePort(),
        generationTimeoutSeconds,
        logName,
      });
      gateways.push(gateway);

      return gateway.url;
    };

    const gatewayUrl = await startGateway(
      "gateway",
      GENERATION_TIMEOUT_SECONDS,
    );

    const realRuntimes: RealRuntimes = {};
    for (const kind of enabled) {
      realRuntimes[kind] = await startRealRuntime(docker, kind);
    }
    const patientGatewayUrl =
      enabled.length > 0
        ? await startGateway(
            "gateway-patient",
            PATIENT_GENERATION_TIMEOUT_SECONDS,
          )
        : null;

    project.provide("realRuntimes", realRuntimes);
    project.provide("stack", {
      redisUrl,
      databaseUrl,
      gatewayUrl,
      patientGatewayUrl,
      runtimeToken,
    });
  } catch (error) {
    await teardown();
    throw error;
  }

  return teardown;
};
