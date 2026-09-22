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
    metrics.recordSettlementPass({
      nextSlotId: null,
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

  it("exports eligible backlog age and clears it when caught up", async () => {
    const metrics = new WorkerMetrics({ collectProcessMetrics: false });
    metrics.recordSettlementPass({
      nextSlotId: "20260820T180000Z-300s-v1",
      processedSlots: 1,
      eligibleBacklogAgeSeconds: 900,
    });
    expect(await metrics.render()).toContain(
      'gradiated_worker_settlement_lag_seconds{service="worker"} 900',
    );
    metrics.recordSettlementPass({
      nextSlotId: null,
      processedSlots: 0,
      eligibleBacklogAgeSeconds: 0,
    });
    expect(await metrics.render()).toContain(
      'gradiated_worker_settlement_lag_seconds{service="worker"} 0',
    );
  });
  it("clears leader-only lag when leadership is released", async () => {
    const metrics = new WorkerMetrics({ collectProcessMetrics: false });
    metrics.setSettlementLeadership(true);
    metrics.recordSettlementPass({
      nextSlotId: null,
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
