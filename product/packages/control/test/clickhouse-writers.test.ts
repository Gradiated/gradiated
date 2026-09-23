import type { InsertResult } from "@clickhouse/client";
import type {
  GenerationSettled,
  ProfilingEventBatch,
} from "@gradiated/contracts";
import { describe, expect, it, vi } from "vitest";
import { ZodError } from "zod";

import { createGenerationWriter } from "../src/clickhouse/generation-ingestion.js";
import { createProfilingWriter } from "../src/clickhouse/profiling-ingestion.js";
import { slotId } from "./support/settlement.js";

const recordingClient = (executed = true) => {
  const result: InsertResult = {
    executed,
    query_id: "query",
    response_headers: {},
  };

  return { insert: vi.fn(async (_params: unknown) => result) };
};

const asyncInsertSettings = (token: string) => ({
  async_insert: 1,
  async_insert_deduplicate: 1,
  insert_deduplication_token: token,
  wait_for_async_insert: 1,
});

const generation: GenerationSettled = {
  generation_id: "0198ad73-a200-7000-8000-000000000001",
  properties: {
    event_schema_version: 2,
    service_tier: "fast",
    external_id: null,
    organization_id: "0198ad73-a200-7000-8000-000000000002",
    workspace_id: "0198ad73-a200-7000-8000-000000000003",
    api_key_id: "0198ad73-a200-7000-8000-000000000004",
    model_id: "kimi-k3",
    served_release_digest: `sha256:${"a".repeat(64)}`,
    status: "succeeded",
    streamed: true,
    pricing: {
      schema_version: 1,
      components: [
        { unit: "input_token", quantity: 10, unit_price: 2, amount: 20 },
        { unit: "output_token", quantity: 3, unit_price: 5, amount: 15 },
      ],
    },
    usage: {
      charge: 35,
      input_tokens: 10,
      cached_input_tokens: 0,
      cache_write_tokens: 0,
      output_tokens: 3,
      reasoning_tokens: 0,
    },
    outcome: {
      finish_reason: "stop",
      error_code: null,
      usable_output_delivered: true,
      cancellation_owner: null,
    },
    timing: {
      received_at: "2026-08-15T12:31:00.000Z",
      started_at: "2026-08-15T12:31:00.100Z",
      first_token_at: "2026-08-15T12:31:00.200Z",
      completed_at: "2026-08-15T12:31:01.000Z",
    },
  },
};

const profilingBatch: ProfilingEventBatch = {
  schema_version: 1,
  batch_id: "0198ad73-a200-7000-8000-000000000010",
  deployment_id: "0198ad73-a200-7000-8000-000000000011",
  model_id: "kimi-k3",
  runtime_revision: "runtime-revision",
  events: [
    {
      id: "0198ad73-a200-7000-8000-000000000012",
      observed_at: "2026-08-15T12:31:00.000Z",
      event_type: "scheduler.batch",
      properties: { batch_size: 4 },
    },
    {
      id: "0198ad73-a200-7000-8000-000000000013",
      observed_at: "2026-08-15T12:31:01.000Z",
      event_type: "kv_cache.usage",
      properties: { used_blocks: 12 },
    },
  ],
};

describe("ClickHouse generation writer", () => {
  it("inserts the generation with its settlement slot, deduplicated by id", async () => {
    const client = recordingClient();

    await createGenerationWriter(client).insertGeneration(generation, slotId);

    expect(client.insert).toHaveBeenCalledExactlyOnceWith({
      table: "generations",
      columns: ["id", "properties"],
      values: [
        {
          id: generation.generation_id,
          properties: {
            ...generation.properties,
            settlement: { slot_id: slotId },
          },
        },
      ],
      format: "JSONEachRow",
      clickhouse_settings: asyncInsertSettings(generation.generation_id),
    });
  });

  it("rejects an invalid settlement slot before the insert", async () => {
    const client = recordingClient();

    await expect(
      createGenerationWriter(client).insertGeneration(
        generation,
        "2026-08-15T12:30:00Z",
      ),
    ).rejects.toBeInstanceOf(ZodError);
    expect(client.insert).not.toHaveBeenCalled();
  });

  it("rejects extra properties before the insert", async () => {
    const client = recordingClient();
    const withPrompt = {
      ...generation,
      properties: { ...generation.properties, prompt: "secret" },
    };

    await expect(
      createGenerationWriter(client).insertGeneration(withPrompt, slotId),
    ).rejects.toBeInstanceOf(ZodError);
    expect(client.insert).not.toHaveBeenCalled();
  });

  it("rejects a charge that does not match the pricing components", async () => {
    const client = recordingClient();
    const overcharged: GenerationSettled = {
      ...generation,
      properties: {
        ...generation.properties,
        usage: { ...generation.properties.usage, charge: 36 },
      },
    };

    await expect(
      createGenerationWriter(client).insertGeneration(overcharged, slotId),
    ).rejects.toBeInstanceOf(ZodError);
    expect(client.insert).not.toHaveBeenCalled();
  });

  it("fails when ClickHouse does not execute the insert", async () => {
    await expect(
      createGenerationWriter(recordingClient(false)).insertGeneration(
        generation,
        slotId,
      ),
    ).rejects.toThrow(
      `ClickHouse did not execute the generations insert ${generation.generation_id}`,
    );
  });
});

describe("ClickHouse profiling writer", () => {
  it("inserts one row per event with the batch fields, deduplicated by batch", async () => {
    const client = recordingClient();

    await createProfilingWriter(client).insertBatch(profilingBatch);

    expect(client.insert).toHaveBeenCalledExactlyOnceWith({
      table: "profiling_events",
      columns: ["id", "properties"],
      values: profilingBatch.events.map((event) => ({
        id: event.id,
        properties: {
          ...event.properties,
          event_schema_version: 1,
          deployment_id: profilingBatch.deployment_id,
          model_id: profilingBatch.model_id,
          runtime_revision: profilingBatch.runtime_revision,
          event_type: event.event_type,
          timing: { observed_at: event.observed_at },
        },
      })),
      format: "JSONEachRow",
      clickhouse_settings: asyncInsertSettings(profilingBatch.batch_id),
    });
  });

  it("rejects an invalid batch before the insert", async () => {
    const client = recordingClient();

    await expect(
      createProfilingWriter(client).insertBatch({
        ...profilingBatch,
        events: [],
      }),
    ).rejects.toBeInstanceOf(ZodError);
    expect(client.insert).not.toHaveBeenCalled();
  });

  it("fails when ClickHouse does not execute the insert", async () => {
    await expect(
      createProfilingWriter(recordingClient(false)).insertBatch(profilingBatch),
    ).rejects.toThrow(
      `ClickHouse did not execute the profiling_events insert ${profilingBatch.batch_id}`,
    );
  });
});
