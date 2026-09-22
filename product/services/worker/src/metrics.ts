import { createServer, type Server } from "node:http";
import {
  collectDefaultMetrics,
  Counter,
  Gauge,
  Histogram,
  Registry,
} from "prom-client";

import type { SettlementPassResult } from "./settlement-loop.js";

export type WorkerLoop = "generation_ingestion" | "settlement";

const operationBuckets = [
  0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60,
];

export class WorkerMetrics {
  readonly registry = new Registry();

  private readonly ingestionLag: Gauge<"kind">;
  private readonly ingestionMessages: Counter<"source">;
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
    this.ingestionLag = new Gauge({
      name: "gradiated_worker_ingestion_backlog",
      help: "Valkey generation-ingestion backlog by kind.",
      labelNames: ["kind"],
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

  recordOperation(loop: WorkerLoop, operation: string, seconds: number): void {
    this.loopOperationDuration.observe({ loop, operation }, seconds);
    this.loopLastSuccess.set({ loop }, Date.now() / 1_000);
  }

  recordIngestedMessages(source: "new" | "recovered", count: number): void {
    if (count > 0) this.ingestionMessages.inc({ source }, count);
  }

  recordIngestionBacklog(
    pending: number,
    unread: number,
    oldestPendingId: string | null,
  ): void {
    this.ingestionLag.set({ kind: "pending" }, pending);
    this.ingestionLag.set({ kind: "unread" }, unread);
    const oldestMilliseconds = oldestPendingId
      ? Number(oldestPendingId.split("-", 1)[0])
      : Number.NaN;
    const ageSeconds = Number.isFinite(oldestMilliseconds)
      ? Math.max(0, Date.now() - oldestMilliseconds) / 1_000
      : 0;
    this.ingestionLag.set({ kind: "oldest_pending_age_seconds" }, ageSeconds);
  }

  setSettlementLeadership(isLeader: boolean): void {
    this.settlementLeader.set(isLeader ? 1 : 0);
    if (!isLeader) this.settlementLag.set(0);
  }

  recordSettlementPass(result: SettlementPassResult): void {
    if (result.processedSlots > 0) {
      this.settlementSlots.inc(result.processedSlots);
    }
    this.settlementLag.set(result.eligibleBacklogAgeSeconds);
  }

  async render(): Promise<string> {
    return this.registry.metrics();
  }
}

export const startWorkerMetricsServer = (
  metrics: WorkerMetrics,
  hostname = "0.0.0.0",
  port = 9_464,
): Server => {
  const server = createServer((request, response) => {
    if (request.method !== "GET" || request.url !== "/metrics") {
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
      () => response.writeHead(500).end(),
    );
  });
  server.listen(port, hostname);
  return server;
};
