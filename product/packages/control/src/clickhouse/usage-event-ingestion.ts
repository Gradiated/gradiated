import { createHash } from "node:crypto";

import type { ClickHouseClient } from "@clickhouse/client";

export interface UsageEventRow {
  eventId: string;
  organizationId: string;
  workspaceId: string;
  product: string;
  sku: string;
  quantity: bigint;
  amountNanoUsd: bigint;
  priceVersion: string;
  occurredAt: Date;
  subjectId: string;
  tags: Record<string, string>;
}

export type UsageEventWriter = {
  insert(rows: UsageEventRow[]): Promise<void>;
};

// DateTime64 parses 'YYYY-MM-DD hh:mm:ss.ffffff' in the column's UTC zone.
const clickHouseTime = (time: Date) =>
  time.toISOString().replace("T", " ").replace("Z", "");

export const createUsageEventWriter = (
  client: Pick<ClickHouseClient, "insert">,
): UsageEventWriter => ({
  async insert(rows) {
    if (rows.length === 0) return;

    const token = createHash("sha256")
      .update(rows.map((row) => row.eventId).join("\n"))
      .digest("hex");
    const result = await client.insert({
      table: "usage_events",
      columns: [
        "event_id",
        "organization_id",
        "workspace_id",
        "product",
        "sku",
        "quantity",
        "amount_nano_usd",
        "price_version",
        "occurred_at",
        "subject_id",
        "tags",
      ],
      values: rows.map((row) => ({
        event_id: row.eventId,
        organization_id: row.organizationId,
        workspace_id: row.workspaceId,
        product: row.product,
        sku: row.sku,
        quantity: row.quantity.toString(),
        amount_nano_usd: row.amountNanoUsd.toString(),
        price_version: row.priceVersion,
        occurred_at: clickHouseTime(row.occurredAt),
        subject_id: row.subjectId,
        tags: row.tags,
      })),
      format: "JSONEachRow",
      clickhouse_settings: {
        async_insert: 1,
        async_insert_deduplicate: 1,
        insert_deduplication_token: token,
        wait_for_async_insert: 1,
      },
    });

    if (!result.executed)
      throw new Error(
        `ClickHouse did not execute the usage_events insert ${token}`,
      );
  },
});
