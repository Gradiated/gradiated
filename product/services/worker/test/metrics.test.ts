import { describe, expect, it } from "vitest";

import { WorkerMetrics } from "../src/metrics.js";

describe("worker metrics", () => {
  it("reports loop health, pipeline progress, lag, and bounded object kinds", async () => {
    const metrics = new WorkerMetrics({ collectProcessMetrics: false });
    metrics.loopStarted("generation_ingestion", false);
    metrics.loopReadyNow("generation_ingestion");
    metrics.recordIngestedMessages("new", 3);
    metrics.recordIngestionBacklog(2, 4, "0-1");
    metrics.recordOperation("generation_ingestion", "consume_pass", 0.25);
    metrics.recordSettlementPass({ nextSlotId: null, processedSlots: 2 }, 100);
    metrics.recordProjection({
      accounts: 1,
      balanceTransactions: 2,
      credentials: 3,
      models: 4,
      workspaces: 5,
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
    expect(body).toContain(
      'gradiated_worker_projection_objects{kind="models",service="worker"} 4',
    );
    expect(body).not.toContain("organization_id");
    expect(body).not.toContain("generation_id");
  });

  it("reports settlement lag only while the pass limit indicates backlog", async () => {
    const metrics = new WorkerMetrics({ collectProcessMetrics: false });
    const nextSlotId = "20260820T180000Z-300s-v1";
    const now = new Date("2026-08-20T18:30:00Z");

    metrics.recordSettlementPass({ nextSlotId, processedSlots: 2 }, 100, now);
    expect(await metrics.render()).toContain(
      'gradiated_worker_settlement_lag_seconds{service="worker"} 0',
    );

    metrics.recordSettlementPass({ nextSlotId, processedSlots: 100 }, 100, now);
    expect(await metrics.render()).toContain(
      'gradiated_worker_settlement_lag_seconds{service="worker"} 1800',
    );
  });
});
