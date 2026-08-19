import {
  createClickHouseRuntimeClient,
  createGenerationWriter,
} from "@gradiated/control";
import { createValkeyClient } from "@gradiated/valkey";
import { rm, writeFile } from "node:fs/promises";
import { parseWorkerEnvironment } from "./environment.js";
import { runGenerationIngestionLoop } from "./generation-ingestion-loop.js";

const environment = parseWorkerEnvironment(process.env);
const abortController = new AbortController();
const readinessPath = "/tmp/gradiated-generation-ingestion-ready";

for (const signal of ["SIGINT", "SIGTERM"] as const) {
  process.once(signal, () => abortController.abort());
}

const valkey = createValkeyClient(environment);
valkey.on("error", (error) => console.error("Valkey client error", error));
await valkey.connect();

const clickhouse = createClickHouseRuntimeClient(environment);
const writer = createGenerationWriter(clickhouse);

const waitForRetry = async (milliseconds: number): Promise<void> => {
  await new Promise<void>((resolve) => {
    const timeout = setTimeout(resolve, milliseconds);
    abortController.signal.addEventListener(
      "abort",
      () => {
        clearTimeout(timeout);
        resolve();
      },
      { once: true },
    );
  });
};

try {
  let retryMilliseconds = 1_000;
  while (!abortController.signal.aborted) {
    try {
      await runGenerationIngestionLoop(
        valkey,
        writer,
        {
          batchSize: environment.GENERATION_BATCH_SIZE,
          claimIdleMs: environment.GENERATION_CLAIM_IDLE_MS,
          consumer: environment.WORKER_CONSUMER_NAME,
          group: environment.GENERATION_CONSUMER_GROUP,
          readBlockMs: environment.GENERATION_READ_BLOCK_MS,
          stream: environment.GENERATION_STREAM_KEY,
          onReady: async () => writeFile(readinessPath, "ready\n", "utf8"),
        },
        abortController.signal,
      );
      retryMilliseconds = 1_000;
    } catch (error) {
      const message =
        error instanceof Error ? error.message.slice(0, 500) : "Unknown error";
      console.error("Generation ingestion loop failed", { message });
      await rm(readinessPath, { force: true });
      await waitForRetry(retryMilliseconds);
      retryMilliseconds = Math.min(retryMilliseconds * 2, 30_000);
    }
  }
} finally {
  await rm(readinessPath, { force: true });
  await Promise.allSettled([clickhouse.close(), valkey.close()]);
}
