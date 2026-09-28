import {
  createClickHouseRuntimeClient,
  createControlDatabase,
  createContentStore,
  createNomadDeploymentStore,
  createTraceCleanup,
  createGenerationSettlementReader,
  createGenerationSettlementStore,
  createGenerationWriter,
} from "@gradiated/control";
import { Gauge } from "prom-client";
import { createValkeyClient } from "@gradiated/valkey";

import {
  ingestionBoundaryMilliseconds,
  readConsumerGroupProgress,
} from "./consumer-group.js";
import {
  parseNomadEnvironment,
  parseWorkerEnvironment,
} from "./environment.js";
import { runGenerationIngestionLoop } from "./generation-ingestion-loop.js";
import {
  observeReplicaReadiness,
  reconcileDeployments,
} from "./deployment-reconciliation.js";
import { createCatalogApply } from "./catalog-apply.js";
import { createNomadGet } from "./nomad-allocations.js";
import { serviceLog } from "./logging.js";
import { startWorkerMetricsServer, WorkerMetrics } from "./metrics.js";
import { runGenerationSettlementLoop } from "./settlement-loop.js";
import { sleep } from "./sleep.js";
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
const { database, pool } = createControlDatabase(environment.DATABASE_URL, 2);
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

if (environment.CONTENTS_BUCKET) {
  const cleanup = createTraceCleanup(
    database,
    createContentStore(environment.CONTENTS_BUCKET),
  );
  supervisors.push(
    supervise({
      loop: "trace_cleanup",
      readinessPath: "/tmp/gradiated-trace-cleanup-ready",
      metrics,
      signal,
      run: async (markReady) => {
        while (!signal.aborted) {
          const start = performance.now();
          await cleanup();
          metrics.recordPass(
            "trace_cleanup",
            (performance.now() - start) / 1000,
          );
          await markReady();
          await sleep(5_000, signal);
        }
      },
    }),
  );
}

const applyCatalog = createCatalogApply(database);
supervisors.push(
  supervise({
    loop: "catalog_apply",
    readinessPath: "/tmp/gradiated-catalog-apply-ready",
    metrics,
    signal,
    run: async (markReady) => {
      while (!signal.aborted) {
        const start = performance.now();
        await applyCatalog();
        metrics.recordPass("catalog_apply", (performance.now() - start) / 1000);
        await markReady();
        await sleep(60_000, signal);
      }
    },
  }),
);

const nomad = parseNomadEnvironment(process.env);
if (nomad) {
  const store = createNomadDeploymentStore(database);
  const certificateExpiry = nomad.NOMAD_CA_KMS_KEY
    ? new Gauge({
        name: "nomad_certificate_expiry_timestamp_seconds",
        help: "Expiry of the worker's current Nomad client certificate.",
        labelNames: ["certificate"],
        registers: [metrics.registry],
      })
    : undefined;
  const get = createNomadGet(nomad, {
    onCertificate: (expires) =>
      certificateExpiry?.set({ certificate: "worker" }, expires),
  });
  supervisors.push(
    supervise({
      loop: "deployment_reconciliation",
      readinessPath: "/tmp/gradiated-deployment-reconciliation-ready",
      metrics,
      signal,
      run: async (markReady) => {
        while (!signal.aborted) {
          const start = performance.now();
          await reconcileDeployments({ store, get, metrics });
          await observeReplicaReadiness({
            store,
            valkey: settlementValkey,
            metrics,
          });
          metrics.recordPass(
            "deployment_reconciliation",
            (performance.now() - start) / 1000,
          );
          await markReady();
          await sleep(5_000, signal);
        }
      },
    }),
  );
}

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
