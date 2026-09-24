import {
  createClickHouseRuntimeClient,
  createControlDatabase,
  createGenerationSettlementReader,
  createGenerationSettlementStore,
  createGenerationWriter,
} from "@gradiated/control";
import { createValkeyClient } from "@gradiated/valkey";

import {
  ingestionBoundaryMilliseconds,
  readConsumerGroupProgress,
} from "./consumer-group.js";
import { parseWorkerEnvironment } from "./environment.js";
import { runGenerationIngestionLoop } from "./generation-ingestion-loop.js";
import { serviceLog } from "./logging.js";
import { startWorkerMetricsServer, WorkerMetrics } from "./metrics.js";
import { runGenerationSettlementLoop } from "./settlement-loop.js";
import { supervise } from "./supervisor.js";

const environment = parseWorkerEnvironment(process.env);
const abortController = new AbortController();
const { signal } = abortController;
const metrics = new WorkerMetrics();
const metricsServer = startWorkerMetricsServer(
  metrics,
  "0.0.0.0",
  environment.METRICS_PORT,
);

metricsServer.once("error", (error) => {
  serviceLog("error", "metrics_server_failed", { error });
  process.exitCode = 1;
  abortController.abort();
});

for (const shutdownSignal of ["SIGINT", "SIGTERM"] as const) {
  process.once(shutdownSignal, () => abortController.abort());
}

const ingestionValkey = createValkeyClient(environment);
const settlementValkey = createValkeyClient(environment);
for (const client of [ingestionValkey, settlementValkey]) {
  client.on("error", (error) =>
    serviceLog("error", "dependency_error", { dependency: "valkey", error }),
  );
  await client.connect();
}

const clickhouse = createClickHouseRuntimeClient(environment);
// Settlement needs one held leader connection; cap all 20 workers at 40 connections.
const { pool } = createControlDatabase(environment.DATABASE_URL, 2);
pool.on("error", (error) =>
  serviceLog("error", "dependency_error", { dependency: "postgres", error }),
);

const consumerGroup = {
  stream: environment.GENERATION_STREAM_KEY,
  group: environment.GENERATION_CONSUMER_GROUP,
};

const pingClickHouse = async (): Promise<void> => {
  const result = await clickhouse.ping({ select: true });
  if (!result.success) throw result.error;
};

const supervisors = [
  supervise({
    loop: "generation_ingestion",
    readinessPath: "/tmp/gradiated-generation-ingestion-ready",
    metrics,
    signal,
    run: (markReady) =>
      runGenerationIngestionLoop({
        client: ingestionValkey,
        writer: createGenerationWriter(clickhouse),
        config: {
          ...consumerGroup,
          consumer: environment.WORKER_CONSUMER_NAME,
          batchSize: environment.GENERATION_BATCH_SIZE,
          claimIdleMs: environment.GENERATION_CLAIM_IDLE_MS,
          readBlockMs: environment.GENERATION_READ_BLOCK_MS,
        },
        telemetry: metrics,
        onReady: markReady,
        signal,
      }),
  }),
  supervise({
    loop: "settlement",
    readinessPath: "/tmp/gradiated-settlement-ready",
    metrics,
    signal,
    run: (markReady) =>
      runGenerationSettlementLoop({
        reader: createGenerationSettlementReader(clickhouse),
        store: createGenerationSettlementStore(pool),
        ingestionBoundary: async () =>
          ingestionBoundaryMilliseconds(
            await readConsumerGroupProgress(settlementValkey, consumerGroup),
          ),
        config: {
          maxSlotsPerPass: environment.SETTLEMENT_MAX_SLOTS_PER_PASS,
          pollMilliseconds: environment.SETTLEMENT_POLL_SECONDS * 1_000,
          settlementDelayMilliseconds:
            environment.SETTLEMENT_DELAY_SECONDS * 1_000,
        },
        telemetry: metrics,
        onReady: async () => {
          await pingClickHouse();
          await markReady();
        },
        signal,
      }),
  }),
];

try {
  await Promise.all(supervisors);
} finally {
  abortController.abort();
  await Promise.allSettled(supervisors);
  metricsServer.close();
  await Promise.allSettled([
    clickhouse.close(),
    ingestionValkey.close(),
    settlementValkey.close(),
    pool.end(),
  ]);
}
