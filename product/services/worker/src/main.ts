import {
  createClickHouseRuntimeClient,
  createControlDatabase,
  createGenerationSettlementReader,
  createGenerationSettlementStore,
  createGenerationWriter,
  createServingReconciliationReader,
  createValkeyServingProjector,
} from "@gradiated/control";
import { createValkeyClient } from "@gradiated/valkey";
import { rm, writeFile } from "node:fs/promises";
import { parseWorkerEnvironment } from "./environment.js";
import { runGenerationIngestionLoop } from "./generation-ingestion-loop.js";
import { runGenerationSettlementLoop } from "./settlement-loop.js";
import { runServingReconciliationLoop } from "./serving-reconciliation-loop.js";

const environment = parseWorkerEnvironment(process.env);
const abortController = new AbortController();
const ingestionReadinessPath = "/tmp/gradiated-generation-ingestion-ready";
const settlementReadinessPath = "/tmp/gradiated-settlement-ready";
const reconciliationReadinessPath =
  "/tmp/gradiated-serving-reconciliation-ready";

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
const reconciliationReader = createServingReconciliationReader(database);
const reconciliationProjector = createValkeyServingProjector(settlementValkey);

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
  name: string,
  readinessPath: string,
  run: () => Promise<void>,
): Promise<void> => {
  let retryMilliseconds = 1_000;
  while (!abortController.signal.aborted) {
    try {
      await run();
      retryMilliseconds = 1_000;
    } catch (error) {
      const message =
        error instanceof Error ? error.message.slice(0, 500) : "Unknown error";
      console.error(`${name} loop failed`, { message });
      await rm(readinessPath, { force: true });
      await waitForRetry(retryMilliseconds);
      retryMilliseconds = Math.min(retryMilliseconds * 2, 30_000);
    }
  }
};

const markSettlementReady = async (): Promise<void> => {
  const result = await clickhouse.ping({ select: true });
  if (!result.success) throw result.error;
  await writeFile(settlementReadinessPath, "ready\n", "utf8");
};

try {
  await Promise.all([
    supervise("Generation ingestion", ingestionReadinessPath, () =>
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
          onReady: async () =>
            writeFile(ingestionReadinessPath, "ready\n", "utf8"),
        },
        abortController.signal,
      ),
    ),
    supervise("Generation settlement", settlementReadinessPath, () =>
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
        },
        abortController.signal,
      ),
    ),
    supervise("Serving reconciliation", reconciliationReadinessPath, () =>
      runServingReconciliationLoop(
        reconciliationReader,
        reconciliationProjector,
        {
          balanceTransactionBatchSize:
            environment.RECONCILIATION_BALANCE_TRANSACTION_BATCH_SIZE,
          pollMilliseconds: environment.RECONCILIATION_POLL_SECONDS * 1_000,
          onReady: async () =>
            writeFile(reconciliationReadinessPath, "ready\n", "utf8"),
        },
        abortController.signal,
      ),
    ),
  ]);
} finally {
  await Promise.all([
    rm(ingestionReadinessPath, { force: true }),
    rm(settlementReadinessPath, { force: true }),
    rm(reconciliationReadinessPath, { force: true }),
  ]);
  await Promise.allSettled([
    clickhouse.close(),
    ingestionValkey.close(),
    settlementValkey.close(),
    pool.end(),
  ]);
}
