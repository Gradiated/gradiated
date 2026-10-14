import type { Server } from "node:http";

import { afterEach, describe, expect, it, vi } from "vitest";

import { startWorkerMetricsServer, WorkerMetrics } from "../src/metrics.js";

const createMetrics = () => new WorkerMetrics({ collectProcessMetrics: false });

describe("worker metrics", () => {
  it("reports loop health, pipeline progress, lag, and bounded object kinds", async () => {
    const metrics = createMetrics();

    metrics.loopStarted("generation_ingestion", false);
    metrics.loopReadyNow("generation_ingestion");
    metrics.recordIngestedMessages("new", 3);
    metrics.recordIngestionBacklog({
      pending: 2,
      unread: 4,
      oldestPendingMilliseconds: 1,
    });
    metrics.recordPass("generation_ingestion", 0.25);
    metrics.recordSettlementPass({
      processedSlots: 2,
      eligibleBacklogAgeSeconds: 0,
    });
    const body = await metrics.render();

    expect(body).toContain('gradiated_worker_service_info{service="worker"} 1');
    expect(body).toContain(
      'gradiated_worker_loop_ready{loop="generation_ingestion",service="worker"} 1',
    );
    expect(body).toContain(
      'gradiated_worker_ingestion_messages_total{source="new",service="worker"} 3',
    );
    expect(body).toContain(
      'gradiated_worker_ingestion_backlog{kind="pending",service="worker"} 2',
    );
    expect(body).toContain("gradiated_worker_operation_duration_seconds_count");
    expect(body).not.toContain("organization_id");
    expect(body).not.toContain("generation_id");
  });

  it("reports replicas and ready replicas per model and drops models that are gone", async () => {
    const metrics = createMetrics();

    metrics.recordReplicaReadiness({ "vendor/old": { replicas: 1, ready: 1 } });
    metrics.recordReplicaReadiness({ "kev/kev-9b": { replicas: 2, ready: 0 } });
    const body = await metrics.render();

    expect(body).toContain(
      'gradiated_worker_model_replicas{model="kev/kev-9b",service="worker"} 2',
    );
    expect(body).toContain(
      'gradiated_worker_model_ready_replicas{model="kev/kev-9b",service="worker"} 0',
    );
    expect(body).not.toContain("vendor/old");
  });

  it("exports a consistent outstanding count and invalidates unknown lag", async () => {
    const metrics = createMetrics();
    vi.useFakeTimers({ now: 120_000 });

    try {
      metrics.recordIngestionBacklog({
        pending: 7,
        unread: 100,
        oldestPendingMilliseconds: null,
      });
      expect(await metrics.render()).toContain(
        'gradiated_worker_ingestion_outstanding_messages{service="worker"} 107',
      );
      expect(await metrics.render()).toContain(
        'gradiated_worker_ingestion_observed_timestamp_seconds{service="worker"} 120',
      );

      vi.setSystemTime(180_000);
      expect(await metrics.render()).toContain(
        'gradiated_worker_ingestion_observed_timestamp_seconds{service="worker"} 120',
      );
      metrics.recordIngestionBacklog({
        pending: 7,
        unread: null,
        oldestPendingMilliseconds: null,
      });
      expect(await metrics.render()).toContain(
        'gradiated_worker_ingestion_observed_timestamp_seconds{service="worker"} 0',
      );
    } finally {
      vi.useRealTimers();
    }
  });

  it("keeps the pass operation labels that dashboards query", async () => {
    const metrics = createMetrics();

    metrics.recordPass("generation_ingestion", 0.1);
    metrics.recordPass("settlement", 0.2);
    const body = await metrics.render();

    expect(body).toContain(
      'gradiated_worker_operation_duration_seconds_count{service="worker",loop="generation_ingestion",operation="consume_pass"} 1',
    );
    expect(body).toContain(
      'gradiated_worker_operation_duration_seconds_count{service="worker",loop="settlement",operation="settlement_pass"} 1',
    );
  });

  it("reports the oldest pending entry age", async () => {
    const metrics = createMetrics();
    vi.useFakeTimers({ now: 10_000 });

    metrics.recordIngestionBacklog({
      pending: 1,
      unread: 0,
      oldestPendingMilliseconds: 4_000,
    });
    vi.useRealTimers();

    expect(await metrics.render()).toContain(
      'gradiated_worker_ingestion_backlog{kind="oldest_pending_age_seconds",service="worker"} 6',
    );
  });

  it("counts deleted entries and drops the unread series when Valkey cannot report it", async () => {
    const metrics = createMetrics();

    metrics.recordDeletedMessages(2);
    metrics.recordIngestionBacklog({
      pending: 0,
      unread: 3,
      oldestPendingMilliseconds: null,
    });
    metrics.recordIngestionBacklog({
      pending: 0,
      unread: null,
      oldestPendingMilliseconds: null,
    });
    const body = await metrics.render();

    expect(body).toContain(
      'gradiated_worker_ingestion_deleted_messages_total{service="worker"} 2',
    );
    expect(body).not.toContain('kind="unread"');
  });

  it("reports no pending age when nothing is pending", async () => {
    const metrics = createMetrics();

    metrics.recordIngestionBacklog({
      pending: 0,
      unread: 0,
      oldestPendingMilliseconds: null,
    });

    expect(await metrics.render()).toContain(
      'gradiated_worker_ingestion_backlog{kind="oldest_pending_age_seconds",service="worker"} 0',
    );
  });

  it("exports eligible backlog age and clears it when caught up", async () => {
    const metrics = createMetrics();

    metrics.recordSettlementPass({
      processedSlots: 1,
      eligibleBacklogAgeSeconds: 900,
    });

    expect(await metrics.render()).toContain(
      'gradiated_worker_settlement_lag_seconds{service="worker"} 900',
    );

    metrics.recordSettlementPass({
      processedSlots: 0,
      eligibleBacklogAgeSeconds: 0,
    });

    expect(await metrics.render()).toContain(
      'gradiated_worker_settlement_lag_seconds{service="worker"} 0',
    );
  });

  it("clears leader-only lag when leadership is released", async () => {
    const metrics = createMetrics();

    metrics.setSettlementLeadership(true);
    metrics.recordSettlementPass({
      processedSlots: 1,
      eligibleBacklogAgeSeconds: 600,
    });

    expect(await metrics.render()).toContain(
      'gradiated_worker_settlement_leader{service="worker"} 1',
    );

    metrics.setSettlementLeadership(false);
    const body = await metrics.render();

    expect(body).toContain(
      'gradiated_worker_settlement_leader{service="worker"} 0',
    );
    expect(body).toContain(
      'gradiated_worker_settlement_lag_seconds{service="worker"} 0',
    );
  });
});

describe("worker metrics server", () => {
  let server: Server | undefined;

  afterEach(async () => {
    vi.restoreAllMocks();

    const stopping = server;
    server = undefined;
    if (stopping) await new Promise((resolve) => stopping.close(resolve));
  });

  const listen = async (
    metrics: WorkerMetrics,
    targets?: () => Promise<unknown>,
    inferenceTargets?: () => Promise<
      readonly { id: string; modelId: string }[]
    >,
  ): Promise<string> => {
    const started = startWorkerMetricsServer(
      metrics,
      "127.0.0.1",
      0,
      targets,
      inferenceTargets,
    );
    server = started;
    await new Promise((resolve) => started.once("listening", resolve));

    const address = started.address();
    if (address === null || typeof address === "string") {
      throw new Error(`Unexpected metrics server address: ${address}`);
    }

    return `http://127.0.0.1:${address.port}`;
  };

  it("serves discovery and fails closed when inventory cannot be read", async () => {
    const groups = [
      { targets: ["host.example"], labels: { deployment: "test" } },
    ];
    const targets = vi
      .fn()
      .mockResolvedValueOnce(groups)
      .mockRejectedValueOnce(new Error("database unavailable"));
    const origin = await listen(createMetrics(), targets);
    const success = await fetch(`${origin}/metrics/targets/lora`);
    expect(success.status).toBe(200);
    expect(await success.json()).toEqual(groups);
    const failed = await fetch(`${origin}/metrics/targets/lora`);
    expect(failed.status).toBe(503);
    expect(await failed.text()).toBe("");
    expect((await fetch(`${origin}/metrics`)).status).toBe(200);
  });

  it.each(["/metrics", "/metrics?timeout=20s"])(
    "serves the registry on GET %s",
    async (path) => {
      const metrics = createMetrics();
      const origin = await listen(metrics);

      const response = await fetch(`${origin}${path}`);

      expect(response.status).toBe(200);
      expect(response.headers.get("content-type")).toBe(
        metrics.registry.contentType,
      );
      expect(await response.text()).toContain("gradiated_worker_service_info");
    },
  );

  it("serves authoritative inference inventory and fails closed on discovery errors", async () => {
    const deployments = [{ id: "test-deployment", modelId: "test/model" }];
    const inventory = vi
      .fn()
      .mockResolvedValueOnce(deployments)
      .mockRejectedValueOnce(new Error("private database connection details"));
    const origin = await listen(createMetrics(), undefined, inventory);

    const success = await fetch(
      `${origin}/metrics/targets/inference?timeout=20s`,
    );
    expect(success.status).toBe(200);
    expect(await success.json()).toEqual(deployments);
    const failed = await fetch(`${origin}/metrics/targets/inference`);
    expect(failed.status).toBe(503);
    expect(await failed.text()).toBe("");
    expect((await fetch(`${origin}/metrics`)).status).toBe(200);
  });

  it.each([
    ["POST", "/metrics"],
    ["GET", "/other"],
    ["GET", "/metrics/targets/inference"],
    ["POST", "/metrics/targets/inference"],
  ])("answers %s %s with 404", async (method, path) => {
    const origin = await listen(createMetrics());

    const response = await fetch(`${origin}${path}`, { method });

    expect(response.status).toBe(404);
  });

  it("answers a failed render with 500 and logs the failure", async () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => undefined);
    const metrics = createMetrics();
    vi.spyOn(metrics, "render").mockRejectedValue(new Error("render failed"));
    const origin = await listen(metrics);

    const response = await fetch(`${origin}/metrics`);

    expect(response.status).toBe(500);
    expect(JSON.parse(String(log.mock.calls[0]?.[0]))).toMatchObject({
      event: "metrics_render_failed",
      level: "error",
      error_type: "Error",
    });
  });
});
