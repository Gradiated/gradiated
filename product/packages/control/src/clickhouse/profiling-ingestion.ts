import type { ClickHouseClient } from "@clickhouse/client";
import {
  ProfilingEventBatchSchema,
  type ProfilingEventBatch,
} from "@gradiated/contracts";

import { insertDeduplicated } from "./client.js";

export type ProfilingWriter = {
  insertBatch(batch: ProfilingEventBatch): Promise<void>;
};

export const createProfilingWriter = (
  client: Pick<ClickHouseClient, "insert">,
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

    await insertDeduplicated(client, {
      table: "profiling_events",
      values: rows,
      token: batch.batch_id,
    });
  },
});
