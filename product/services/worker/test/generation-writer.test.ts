import {
  createGenerationWriter,
  storedGenerationPropertiesSchema,
} from "@gradiated/control";
import type { GenerationSettled } from "@gradiated/contracts";
import { describe, expect, it, vi } from "vitest";

const event = {
  generation_id: "0198ad73-a200-7000-8000-000000000001",
  properties: {
    event_schema_version: 1,
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
      ],
    },
    usage: {
      charge: 20,
      input_tokens: 10,
      cached_input_tokens: 0,
      cache_write_tokens: 0,
      output_tokens: 0,
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
} satisfies GenerationSettled;

describe("ClickHouse generation writer", () => {
  it("validates the stored properties document", () => {
    expect(
      storedGenerationPropertiesSchema.parse({
        ...event.properties,
        settlement: { slot_id: "20260815T123000Z-300s-v1" },
      }),
    ).toBeDefined();
  });

  it("rejects a charge that does not match the pricing components", () => {
    expect(() =>
      storedGenerationPropertiesSchema.parse({
        ...event.properties,
        usage: { ...event.properties.usage, charge: 21 },
        settlement: { slot_id: "20260815T123000Z-300s-v1" },
      }),
    ).toThrow();
  });

  it("uses acknowledged asynchronous insert settings", async () => {
    const insert = vi.fn(async () => ({ executed: true }));
    const writer = createGenerationWriter({ insert } as never);

    await writer.insertGeneration(event, "20260815T123000Z-300s-v1");

    expect(insert).toHaveBeenCalledWith(
      expect.objectContaining({
        clickhouse_settings: {
          async_insert: 1,
          async_insert_deduplicate: 1,
          insert_deduplication_token: event.generation_id,
          wait_for_async_insert: 1,
        },
      }),
    );
  });

  it("rejects an invalid row before the insert", async () => {
    const insert = vi.fn();
    const writer = createGenerationWriter({ insert } as never);

    await expect(
      writer.insertGeneration(
        {
          ...event,
          properties: { ...event.properties, prompt: "secret" },
        } as never,
        "20260815T123000Z-300s-v1",
      ),
    ).rejects.toBeDefined();
    expect(insert).not.toHaveBeenCalled();
  });
});
