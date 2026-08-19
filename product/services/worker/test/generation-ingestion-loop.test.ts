import type { GenerationWriter } from "@gradiated/control";
import { describe, expect, it, vi } from "vitest";
import {
  deriveSettlementSlotId,
  getSafeTrimThreshold,
  nextStreamId,
  parseGenerationStreamMessage,
  processGenerationMessage,
} from "../src/generation-ingestion-loop.js";

const generationId = "0198ad73-a200-7000-8000-000000000001";
const properties = {
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
} as const;

const entry = {
  id: "1786797061000-4",
  message: {
    generation_id: generationId,
    properties: JSON.stringify(properties),
  },
};

describe("generation ingestion", () => {
  it("derives the shared five-minute settlement slot", () => {
    expect(deriveSettlementSlotId(entry.id)).toBe("20260815T123000Z-300s-v1");
  });

  it("rejects an invalid stream ID", () => {
    expect(() => deriveSettlementSlotId("not-an-id")).toThrow(
      "Invalid Valkey Stream ID",
    );
  });

  it("validates the complete stream event", () => {
    expect(parseGenerationStreamMessage(entry)).toEqual({
      generation_id: generationId,
      properties,
    });
  });

  it("rejects extra stream fields", () => {
    expect(() =>
      parseGenerationStreamMessage({
        ...entry,
        message: { ...entry.message, prompt: "secret" },
      }),
    ).toThrow("Invalid generation stream fields");
  });

  it("acknowledges only after ClickHouse accepts the insert", async () => {
    const calls: string[] = [];
    const writer: GenerationWriter = {
      insertGeneration: vi.fn(async () => {
        calls.push("insert");
      }),
    };
    const client = {
      xAck: vi.fn(async () => {
        calls.push("ack");
        return 1;
      }),
    };

    await processGenerationMessage(
      client as never,
      writer,
      { group: "group", stream: "stream" },
      entry,
    );

    expect(calls).toEqual(["insert", "ack"]);
  });

  it("does not acknowledge a failed insert", async () => {
    const writer: GenerationWriter = {
      insertGeneration: vi.fn(async () => {
        throw new Error("ClickHouse unavailable");
      }),
    };
    const client = { xAck: vi.fn() };

    await expect(
      processGenerationMessage(
        client as never,
        writer,
        { group: "group", stream: "stream" },
        entry,
      ),
    ).rejects.toThrow("ClickHouse unavailable");
    expect(client.xAck).not.toHaveBeenCalled();
  });

  it("keeps the oldest pending entry during trimming", () => {
    expect(getSafeTrimThreshold("100-2", "200-4")).toBe("100-2");
  });

  it("trims through the last delivered entry when none are pending", () => {
    expect(getSafeTrimThreshold(null, "200-4")).toBe("200-5");
    expect(nextStreamId("200-4")).toBe("200-5");
    expect(getSafeTrimThreshold(null, "0-0")).toBeNull();
  });
});
