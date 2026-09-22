import {
  createClickHouseRuntimeClient,
  createControlDatabase,
  createGenerationSettlementReader,
  createGenerationSettlementStore,
  createGenerationWriter,
} from "@gradiated/control";
import { createValkeyClient } from "@gradiated/valkey";
import { rm, writeFile } from "node:fs/promises";
import { parseWorkerEnvironment } from "./environment.js";
import { runGenerationIngestionLoop } from "./generation-ingestion-loop.js";
import { runGenerationSettlementLoop } from "./settlement-loop.js";
import {
  startWorkerMetricsServer,
  WorkerMetrics,
  type WorkerLoop,
} from "./metrics.js";

const environment = parseWorkerEnvironment(process.env);
const abortController = new AbortController();
const metrics = new WorkerMetrics();
const metricsPort = Number(process.env.METRICS_PORT ?? "9464");
const metricsServer = startWorkerMetricsServer(metrics, "0.0.0.0", metricsPort);
const ingestionReadinessPath = "/tmp/gradiated-generation-ingestion-ready";
const settlementReadinessPath = "/tmp/gradiated-settlement-ready";

for (const signal of ["SIGINT", "SIGTERM"] as const) {
  process.once(signal, () => abortController.abort());
}

const ingestionValkey = createValkeyClient(environment);
const settlementValkey = createValkeyClient(environment);
for (const client of [ingestionValkey, settlementValkey]) {
  client.on("error", (error) => console.error("Valkey client error", error));
  await client.connect();
}

const clickhouse = createClickHouseRuntimeClient(environment);
const writer = createGenerationWriter(clickhouse);
const settlementReader = createGenerationSettlementReader(clickhouse);
const { database, pool } = createControlDatabase(environment.DATABASE_URL);
const settlementStore = createGenerationSettlementStore(pool);

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

const supervise = async (
  displayName: string,
  loop: WorkerLoop,
  readinessPath: string,
  run: () => Promise<void>,
): Promise<void> => {
  let retryMilliseconds = 1_000;
  let attempt = 0;
  while (!abortController.signal.aborted) {
    metrics.loopStarted(loop, attempt > 0);
    attempt += 1;
    try {
      await run();
      retryMilliseconds = 1_000;
    } catch (error) {
      const message =
        error instanceof Error ? error.message.slice(0, 500) : "Unknown error";
      console.error(`${displayName} loop failed`, { message });
      metrics.loopFailed(loop);
      await rm(readinessPath, { force: true });
      await waitForRetry(retryMilliseconds);
      retryMilliseconds = Math.min(retryMilliseconds * 2, 30_000);
    }
  }
  metrics.loopStopped(loop);
};

const markSettlementReady = async (): Promise<void> => {
  const result = await clickhouse.ping({ select: true });
  if (!result.success) throw result.error;
  await writeFile(settlementReadinessPath, "ready\n", "utf8");
  metrics.loopReadyNow("settlement");
};

try {
  await Promise.all([
    supervise(
      "Generation ingestion",
      "generation_ingestion",
      ingestionReadinessPath,
      () =>
        runGenerationIngestionLoop(
          ingestionValkey,
          writer,
          {
            batchSize: environment.GENERATION_BATCH_SIZE,
            claimIdleMs: environment.GENERATION_CLAIM_IDLE_MS,
            consumer: environment.WORKER_CONSUMER_NAME,
            group: environment.GENERATION_CONSUMER_GROUP,
            readBlockMs: environment.GENERATION_READ_BLOCK_MS,
            stream: environment.GENERATION_STREAM_KEY,
            onReady: async () => {
              await writeFile(ingestionReadinessPath, "ready\n", "utf8");
              metrics.loopReadyNow("generation_ingestion");
            },
            onBacklog: (pending, unread, oldestPendingId) =>
              metrics.recordIngestionBacklog(pending, unread, oldestPendingId),
            onMessagesProcessed: (source, count) =>
              metrics.recordIngestedMessages(source, count),
            onPass: (duration) =>
              metrics.recordOperation(
                "generation_ingestion",
                "consume_pass",
                duration,
              ),
          },
          abortController.signal,
        ),
    ),
    supervise(
      "Generation settlement",
      "settlement",
      settlementReadinessPath,
      () =>
        runGenerationSettlementLoop(
          settlementReader,
          settlementStore,
          settlementValkey,
          {
            consumerGroup: environment.GENERATION_CONSUMER_GROUP,
            maxSlotsPerPass: environment.SETTLEMENT_MAX_SLOTS_PER_PASS,
            pollMilliseconds: environment.SETTLEMENT_POLL_SECONDS * 1_000,
            settlementDelayMilliseconds:
              environment.SETTLEMENT_DELAY_SECONDS * 1_000,
            stream: environment.GENERATION_STREAM_KEY,
            onReady: markSettlementReady,
            onLeadership: (isLeader) =>
              metrics.setSettlementLeadership(isLeader),
            onPass: (result, duration) => {
              metrics.recordSettlementPass(result);
              metrics.recordOperation(
                "settlement",
                "settlement_pass",
                duration,
              );
            },
          },
          abortController.signal,
        ),
    ),
  ]);
} finally {
  metricsServer.close();
  await Promise.all([
    rm(ingestionReadinessPath, { force: true }),
    rm(settlementReadinessPath, { force: true }),
  ]);
  await Promise.allSettled([
    clickhouse.close(),
    ingestionValkey.close(),
    settlementValkey.close(),
    pool.end(),
  ]);
}
