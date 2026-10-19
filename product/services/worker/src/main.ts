import {
  createClickHouseRuntimeClient,
  createControlDatabase,
  createWorkspaceApiKeyService,
  createContentStore,
  createDeploymentStore,
  createKubernetesDeploymentStore,
  createTraceCleanup,
  createTrainingArtifactCleanup,
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
import { observeReplicaReadiness } from "./deployment-reconciliation.js";
import { createCatalogApply } from "./catalog-apply.js";
import {
  createKubernetesDeploymentView,
  createKubernetesGet,
  createKubernetesRequest,
} from "./kubernetes-deployments.js";
import {
  qualifyKubernetesPod,
  runSdkQualification,
} from "./kubernetes-qualification.js";
import { serviceLog } from "./logging.js";
import { loraMetricsTargets } from "./lora-metrics-targets.js";
import { startWorkerMetricsServer, WorkerMetrics } from "./metrics.js";
import { runGenerationSettlementLoop } from "./settlement-loop.js";
import { probeModel } from "./inference-probe.js";
import {
  InferenceProbeMetrics,
  runInferenceProbes,
} from "./inference-probes.js";
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
  async () =>
    loraMetricsTargets(
      await createDeploymentStore(database).adapterMetricsTargets(),
    ),
  async () =>
    (await createDeploymentStore(database).replicas()).map(
      ({ id, modelId }) => ({ id, modelId }),
    ),
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

if (environment.TRAINING_ARTIFACTS_BUCKET) {
  const cleanup = createTrainingArtifactCleanup(
    database,
    createContentStore(environment.TRAINING_ARTIFACTS_BUCKET),
  );
  supervisors.push(
    supervise({
      loop: "training_artifact_cleanup",
      readinessPath: "/tmp/gradiated-training-artifact-cleanup-ready",
      metrics,
      signal,
      run: async (markReady) => {
        while (!signal.aborted) {
          const start = performance.now();
          await cleanup();
          metrics.recordPass(
            "training_artifact_cleanup",
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

if (process.env.GPU_KUBERNETES_NAMESPACE) {
  const namespace = process.env.GPU_KUBERNETES_NAMESPACE;
  const store = createKubernetesDeploymentStore(database);
  const view = createKubernetesDeploymentView(
    process.env.GPU_KUBERNETES_NAMESPACE,
    createKubernetesGet(signal),
  );
  supervisors.push(
    supervise({
      loop: "kubernetes_deployment_reconciliation",
      readinessPath:
        "/tmp/gradiated-kubernetes-deployment-reconciliation-ready",
      metrics,
      signal,
      run: async (markReady) => {
        while (!signal.aborted) {
          const start = performance.now();
          const result = await store.reconcile(view);
          if (result) metrics.recordReconciliation(result.written);
          await observeReplicaReadiness({
            store: createDeploymentStore(database),
            valkey: settlementValkey,
            metrics,
          });
          metrics.recordPass(
            "kubernetes_deployment_reconciliation",
            (performance.now() - start) / 1000,
          );
          await markReady();
          await sleep(5_000, signal);
        }
      },
    }),
  );
  const request = createKubernetesRequest(signal);
  supervisors.push(
    supervise({
      loop: "kubernetes_qualification",
      readinessPath: "/tmp/gradiated-kubernetes-qualification-ready",
      metrics,
      signal,
      run: async (markReady) => {
        const qualificationPool = createControlDatabase(
          environment.DATABASE_URL,
          1,
        ).pool;
        qualificationPool.on("error", (error) =>
          serviceLog("error", "dependency_error", {
            dependency: "postgres",
            error,
          }),
        );
        try {
          while (!signal.aborted) {
            const client = await qualificationPool.connect();
            let locked = false;
            try {
              const result = await client.query<{ locked: boolean }>(
                "select pg_try_advisory_lock(hashtext('gpu-qualification-v1')) as locked",
              );
              locked = result.rows[0]?.locked === true;
              if (locked)
                await qualifyKubernetesPod(namespace, request, (input) =>
                  runSdkQualification(input, signal),
                );
            } finally {
              if (locked)
                await client
                  .query(
                    "select pg_advisory_unlock(hashtext('gpu-qualification-v1'))",
                  )
                  .catch(() => undefined);
              client.release();
            }
            await markReady();
            await sleep(10_000, signal);
          }
        } finally {
          await qualificationPool.end();
        }
      },
    }),
  );
}

if (environment.INFERENCE_PROBE_BASE_URL) {
  const baseURL = environment.INFERENCE_PROBE_BASE_URL;
  const userId = environment.MODEL_VERIFICATION_USER_ID!;
  const workspaceId = environment.MODEL_VERIFICATION_WORKSPACE_ID!;
  const keys = createWorkspaceApiKeyService(database);
  const store = createDeploymentStore(database);
  const probeMetrics = new InferenceProbeMetrics(metrics.registry);
  supervisors.push(
    supervise({
      loop: "inference_probes",
      readinessPath: "/tmp/gradiated-inference-probes-ready",
      metrics,
      signal,
      run: async (markReady) => {
        let issued: Awaited<ReturnType<typeof keys.createApiKey>> | undefined;
        let refreshAt = 0;
        try {
          await runInferenceProbes({
            eval: (script, options) => settlementValkey.eval(script, options),
            replicas: () => store.replicas(),
            beforePass: async () => {
              if (issued && Date.now() < refreshAt) return;

              const previous = issued;
              issued = await keys.createApiKey(userId, workspaceId, {
                name: "Public inference monitoring",
                expiresAt: new Date(Date.now() + 15 * 60_000),
              });
              refreshAt = Date.now() + 10 * 60_000;
              if (previous)
                await keys.revokeApiKey(
                  userId,
                  workspaceId,
                  previous.apiKey.id,
                );
            },
            probe: (replica, probeSignal) =>
              probeModel({
                apiKey: issued!.secret,
                baseURL,
                modelId: replica.modelId,
                deploymentId: replica.id,
                protocol: replica.release.protocol,
                signal: probeSignal,
              }),
            metrics: probeMetrics,
            signal,
            onReady: async (durationSeconds) => {
              metrics.recordPass("inference_probes", durationSeconds);
              await markReady();
            },
          });
        } finally {
          if (issued)
            await keys.revokeApiKey(userId, workspaceId, issued.apiKey.id);
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
