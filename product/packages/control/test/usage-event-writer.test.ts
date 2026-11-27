import { describe, expect, it, vi } from "vitest";

import { createUsageEventWriter } from "../src/clickhouse/usage-event-ingestion.js";

const row = {
  eventId: "training:run-usage:run_1:1:1048576",
  organizationId: "0198ad73-a200-7000-8000-000000000002",
  workspaceId: "0198ad73-a200-7000-8000-000000000003",
  product: "training",
  sku: "train:qwen/qwen3-8b",
  quantity: 1_048_576n,
  amountNanoUsd: 419_430_400n,
  priceVersion: "pv_training_2026_11_27_placeholder",
  occurredAt: new Date("2026-11-27T12:00:00.123Z"),
  subjectId: "run_1",
  tags: { attempt: "1" },
};

const client = (executed = true) => ({
  insert: vi.fn(async (_params: unknown) => ({
    executed,
    query_id: "query",
    response_headers: {},
  })),
});

describe("usage event writer", () => {
  it("writes the events with a token that is stable across retries", async () => {
    const recording = client();
    const writer = createUsageEventWriter(recording);

    await writer.insert([row]);
    await writer.insert([row]);

    const [first, second] = recording.insert.mock.calls.map(
      ([params]) => params,
    );
    expect(first).toEqual(second);
    expect(first).toMatchObject({
      table: "usage_events",
      format: "JSONEachRow",
      values: [
        {
          event_id: row.eventId,
          organization_id: row.organizationId,
          workspace_id: row.workspaceId,
          product: "training",
          sku: "train:qwen/qwen3-8b",
          quantity: "1048576",
          amount_nano_usd: "419430400",
          price_version: row.priceVersion,
          occurred_at: "2026-11-27 12:00:00.123",
          subject_id: "run_1",
          tags: { attempt: "1" },
        },
      ],
      clickhouse_settings: {
        async_insert: 1,
        wait_for_async_insert: 1,
        insert_deduplication_token: expect.stringMatching(/^[0-9a-f]{64}$/),
      },
    });
  });

  it("writes nothing for no events", async () => {
    const recording = client();

    await createUsageEventWriter(recording).insert([]);

    expect(recording.insert).not.toHaveBeenCalled();
  });

  it("fails when ClickHouse does not execute the insert", async () => {
    await expect(
      createUsageEventWriter(client(false)).insert([row]),
    ).rejects.toThrow("did not execute");
  });
});
