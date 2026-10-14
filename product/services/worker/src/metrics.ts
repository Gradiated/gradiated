import { createServer, type Server } from "node:http";
import {
  collectDefaultMetrics,
  Counter,
  Gauge,
  Histogram,
  Registry,
} from "prom-client";

import { serviceLog } from "./logging.js";

export type WorkerLoop =
  | "generation_ingestion"
  | "settlement"
  | "trace_cleanup"
  | "kubernetes_deployment_reconciliation"
  | "kubernetes_qualification"
  | "catalog_apply"
  | "inference_probes";

export type IngestionSource = "new" | "recovered";

export type IngestionBacklog = {
  pending: number;
  unread: number | null;
  oldestPendingMilliseconds: number | null;
};

export type SettlementPassSummary = {
  processedSlots: number;
  eligibleBacklogAgeSeconds: number;
};

const passOperation: Record<WorkerLoop, string> = {
  generation_ingestion: "consume_pass",
  settlement: "settlement_pass",
  trace_cleanup: "cleanup_pass",
  kubernetes_deployment_reconciliation: "kubernetes_reconcile_pass",
  kubernetes_qualification: "kubernetes_qualification_pass",
  catalog_apply: "apply_pass",
  inference_probes: "probe_pass",
};

const operationBuckets = [
  0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60,
];

export class WorkerMetrics {
  readonly registry = new Registry();

  private readonly ingestionDemand: Gauge;
  private readonly ingestionObservation: Gauge;
  private readonly ingestionLag: Gauge<"kind">;
  private readonly ingestionMessages: Counter<"source">;
  private readonly ingestionDeletedMessages: Counter;
  private readonly routedDeployments: Gauge;
  private readonly modelReplicas: Gauge<"model">;
  private readonly modelReadyReplicas: Gauge<"model">;
  private readonly loopFailures: Counter<"loop">;
  private readonly loopLastSuccess: Gauge<"loop">;
  private readonly loopOperationDuration: Histogram<"loop" | "operation">;
  private readonly loopReady: Gauge<"loop">;
  private readonly loopRestarts: Counter<"loop">;
  private readonly loopUp: Gauge<"loop">;
  private readonly settlementLag: Gauge;
  private readonly settlementLeader: Gauge;
  private readonly settlementSlots: Counter;

  constructor(options: { collectProcessMetrics?: boolean } = {}) {
    this.registry.setDefaultLabels({ service: "worker" });
    new Gauge({
      name: "gradiated_worker_service_info",
      help: "Constant service identity metric used to detect missing worker telemetry.",
      registers: [this.registry],
    }).set(1);
    this.loopUp = new Gauge({
      name: "gradiated_worker_loop_up",
      help: "Whether a supervised worker loop is currently running.",
      labelNames: ["loop"],
      registers: [this.registry],
    });
    this.loopReady = new Gauge({
      name: "gradiated_worker_loop_ready",
      help: "Whether a worker loop has completed its dependency and startup checks.",
      labelNames: ["loop"],
      registers: [this.registry],
    });
    this.loopFailures = new Counter({
      name: "gradiated_worker_loop_failures_total",
      help: "Supervised worker loop failures.",
      labelNames: ["loop"],
      registers: [this.registry],
    });
    this.loopRestarts = new Counter({
      name: "gradiated_worker_loop_restarts_total",
      help: "Worker loop restarts after an earlier attempt ended.",
      labelNames: ["loop"],
      registers: [this.registry],
    });
    this.loopLastSuccess = new Gauge({
      name: "gradiated_worker_loop_last_success_timestamp_seconds",
      help: "Unix timestamp of the latest successful worker loop pass.",
      labelNames: ["loop"],
      registers: [this.registry],
    });
    this.loopOperationDuration = new Histogram({
      name: "gradiated_worker_operation_duration_seconds",
      help: "Duration of bounded worker operations.",
      labelNames: ["loop", "operation"],
      buckets: operationBuckets,
      registers: [this.registry],
    });
    this.ingestionMessages = new Counter({
      name: "gradiated_worker_ingestion_messages_total",
      help: "Generation settlement messages inserted into ClickHouse and acknowledged.",
      labelNames: ["source"],
      registers: [this.registry],
    });
    this.ingestionDeletedMessages = new Counter({
      name: "gradiated_worker_ingestion_deleted_messages_total",
      help: "Pending generation messages that left the stream before ClickHouse ingested them.",
      registers: [this.registry],
    });
    this.ingestionDemand = new Gauge({
      name: "gradiated_worker_ingestion_outstanding_messages",
      help: "Shared unread plus pending messages from one consumer-group snapshot.",
      registers: [this.registry],
    });
    this.ingestionObservation = new Gauge({
      name: "gradiated_worker_ingestion_observed_timestamp_seconds",
      help: "Latest valid backlog observation; zero means unknown or unobserved.",
      registers: [this.registry],
    });
    this.ingestionLag = new Gauge({
      name: "gradiated_worker_ingestion_backlog",
      help: "Valkey generation-ingestion backlog by kind.",
      labelNames: ["kind"],
      registers: [this.registry],
    });
    this.routedDeployments = new Gauge({
      name: "gradiated_worker_routed_deployments",
      help: "Model deployments registered by Kubernetes reconciliation.",
      registers: [this.registry],
    });
    this.modelReplicas = new Gauge({
      name: "gradiated_worker_model_replicas",
      help: "Available model replicas per model.",
      labelNames: ["model"],
      registers: [this.registry],
    });
    this.modelReadyReplicas = new Gauge({
      name: "gradiated_worker_model_ready_replicas",
      help: "Model replicas with a fresh, healthy status for their release.",
      labelNames: ["model"],
      registers: [this.registry],
    });
    this.settlementSlots = new Counter({
      name: "gradiated_worker_settlement_slots_total",
      help: "Five-minute settlement slots processed.",
      registers: [this.registry],
    });
    this.settlementLeader = new Gauge({
      name: "gradiated_worker_settlement_leader",
      help: "Whether this worker currently owns settlement leadership.",
      registers: [this.registry],
    });
    this.settlementLeader.set(0);
    this.settlementLag = new Gauge({
      name: "gradiated_worker_settlement_lag_seconds",
      help: "Age beyond the settlement delay of the oldest eligible unsettled slot.",
      registers: [this.registry],
    });
    if (options.collectProcessMetrics !== false) {
      collectDefaultMetrics({
        prefix: "gradiated_worker_",
        register: this.registry,
      });
    }
  }

  loopStarted(loop: WorkerLoop, restart: boolean): void {
    this.loopUp.set({ loop }, 1);
    this.loopReady.set({ loop }, 0);
    if (restart) this.loopRestarts.inc({ loop });
  }

  loopFailed(loop: WorkerLoop): void {
    this.loopFailures.inc({ loop });
    this.loopUp.set({ loop }, 0);
    this.loopReady.set({ loop }, 0);
  }

  loopStopped(loop: WorkerLoop): void {
    this.loopUp.set({ loop }, 0);
    this.loopReady.set({ loop }, 0);
  }

  loopReadyNow(loop: WorkerLoop): void {
    this.loopReady.set({ loop }, 1);
    this.loopLastSuccess.set({ loop }, Date.now() / 1_000);
  }

  recordPass(loop: WorkerLoop, seconds: number): void {
    this.loopOperationDuration.observe(
      { loop, operation: passOperation[loop] },
      seconds,
    );
    this.loopLastSuccess.set({ loop }, Date.now() / 1_000);
  }

  recordReconciliation(routed: number): void {
    this.routedDeployments.set(routed);
  }

  recordReplicaReadiness(
    byModel: Readonly<Record<string, { replicas: number; ready: number }>>,
  ): void {
    this.modelReplicas.reset();
    this.modelReadyReplicas.reset();
    for (const [model, { replicas, ready }] of Object.entries(byModel)) {
      this.modelReplicas.set({ model }, replicas);
      this.modelReadyReplicas.set({ model }, ready);
    }
  }

  recordIngestedMessages(source: IngestionSource, count: number): void {
    if (count > 0) this.ingestionMessages.inc({ source }, count);
  }

  recordDeletedMessages(count: number): void {
    if (count > 0) this.ingestionDeletedMessages.inc(count);
  }

  recordIngestionBacklog({
    pending,
    unread,
    oldestPendingMilliseconds,
  }: IngestionBacklog): void {
    const oldestPendingAgeSeconds =
      oldestPendingMilliseconds === null
        ? 0
        : Math.max(0, Date.now() - oldestPendingMilliseconds) / 1_000;

    // Unknown lag must invalidate autoscaling, rather than look like an empty queue.
    this.ingestionDemand.set(unread === null ? 0 : pending + unread);
    this.ingestionObservation.set(unread === null ? 0 : Date.now() / 1_000);
    this.ingestionLag.set({ kind: "pending" }, pending);
    if (unread === null) this.ingestionLag.remove({ kind: "unread" });
    else this.ingestionLag.set({ kind: "unread" }, unread);
    this.ingestionLag.set(
      { kind: "oldest_pending_age_seconds" },
      oldestPendingAgeSeconds,
    );
  }

  setSettlementLeadership(isLeader: boolean): void {
    this.settlementLeader.set(isLeader ? 1 : 0);
    if (!isLeader) this.settlementLag.set(0);
  }

  recordSettlementPass({
    processedSlots,
    eligibleBacklogAgeSeconds,
  }: SettlementPassSummary): void {
    if (processedSlots > 0) this.settlementSlots.inc(processedSlots);

    this.settlementLag.set(eligibleBacklogAgeSeconds);
  }

  async render(): Promise<string> {
    return this.registry.metrics();
  }
}

export const stopwatch = (): (() => number) => {
  const started = process.hrtime.bigint();

  return () => Number(process.hrtime.bigint() - started) / 1e9;
};

export const startWorkerMetricsServer = (
  metrics: WorkerMetrics,
  hostname: string,
  port: number,
  targets?: () => Promise<unknown>,
  inferenceTargets?: () => Promise<readonly { id: string; modelId: string }[]>,
): Server => {
  const server = createServer((request, response) => {
    const pathname = request.url?.split("?", 1)[0];

    if (
      request.method === "GET" &&
      pathname === "/metrics/targets/inference" &&
      inferenceTargets
    ) {
      void inferenceTargets().then(
        (deployments) => {
          const body = JSON.stringify(deployments);
          response
            .writeHead(200, {
              "Content-Type": "application/json",
              "Content-Length": Buffer.byteLength(body),
            })
            .end(body);
        },
        (error: unknown) => {
          serviceLog("error", "inference_probe_discovery_failed", { error });
          response.writeHead(503).end();
        },
      );
      return;
    }

    if (
      request.method === "GET" &&
      pathname === "/metrics/targets/lora" &&
      targets
    ) {
      void targets().then(
        (groups) => {
          const body = JSON.stringify(groups);
          response
            .writeHead(200, {
              "Content-Type": "application/json",
              "Content-Length": Buffer.byteLength(body),
            })
            .end(body);
        },
        (error: unknown) => {
          serviceLog("error", "lora_metrics_discovery_failed", { error });
          response.writeHead(503).end();
        },
      );
      return;
    }

    if (request.method !== "GET" || pathname !== "/metrics") {
      response.writeHead(404).end();
      return;
    }

    void metrics.render().then(
      (body) => {
        response.writeHead(200, {
          "Content-Type": metrics.registry.contentType,
          "Content-Length": Buffer.byteLength(body),
        });
        response.end(body);
      },
      (error: unknown) => {
        serviceLog("error", "metrics_render_failed", { error });
        response.writeHead(500).end();
      },
    );
  });

  server.listen(port, hostname);

  return server;
};
