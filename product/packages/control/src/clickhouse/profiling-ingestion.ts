import type { ClickHouseClient } from "@clickhouse/client";
import {
  ProfilingEventBatchSchema,
  type ProfilingEventBatch,
} from "@gradiated/contracts";

export type ProfilingWriter = {
  insertBatch(batch: ProfilingEventBatch): Promise<void>;
};

export const createProfilingWriter = (
  client: ClickHouseClient,
): ProfilingWriter => ({
  async insertBatch(input) {
    const batch = ProfilingEventBatchSchema.parse(input);
    const rows = batch.events.map((event) => ({
      id: event.id,
      properties: {
        ...event.properties,
        event_schema_version: batch.schema_version,
        deployment_id: batch.deployment_id,
        model_id: batch.model_id,
        runtime_revision: batch.runtime_revision,
        event_type: event.event_type,
        timing: {
          observed_at: event.observed_at,
        },
      },
    }));
    const result = await client.insert({
      table: "profiling_events",
      columns: ["id", "properties"],
      values: rows,
      format: "JSONEachRow",
      clickhouse_settings: {
        async_insert: 1,
        async_insert_deduplicate: 1,
        insert_deduplication_token: batch.batch_id,
        wait_for_async_insert: 1,
      },
    });
    if (!result.executed) {
      throw new Error(`ClickHouse did not execute profiling batch ${batch.batch_id}`);
    }
  },
});
