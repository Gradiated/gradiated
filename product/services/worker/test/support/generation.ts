import {
  createGenerationWriter,
  storedGenerationPropertiesSchema,
} from "@gradiated/control";
import type { GenerationSettled } from "@gradiated/contracts";
import { vi } from "vitest";
import { z } from "zod";

import type { IngestionTelemetry } from "../../src/generation-ingestion-loop.js";

type VersionOneProperties = Extract<
  GenerationSettled["properties"],
  { event_schema_version: 1 }
>;
type ClickHouseInsertClient = Parameters<typeof createGenerationWriter>[0];
type ClickHouseInsertResult = Awaited<
  ReturnType<ClickHouseInsertClient["insert"]>
>;

export const generationSettled = (
  overrides: Partial<Pick<GenerationSettled, "generation_id">> & {
    properties?: Partial<VersionOneProperties>;
  } = {},
): GenerationSettled => ({
  generation_id:
    overrides.generation_id ?? "0198ad73-a200-7000-8000-000000000001",
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
    ...overrides.properties,
  },
});

export const streamFields = (
  event: GenerationSettled,
): Record<string, string> => ({
  generation_id: event.generation_id,
  properties: JSON.stringify(event.properties),
});

export const mispricedFields = (
  event: GenerationSettled,
): Record<string, string> =>
  streamFields({
    ...event,
    properties: {
      ...event.properties,
      usage: { ...event.properties.usage, charge: 21 },
    },
  });

const insertedRowSchema = z.object({
  id: z.string(),
  properties: storedGenerationPropertiesSchema,
});

export type InsertedGeneration = { id: string; slotId: string };

export const recordingClickHouse = () => {
  const inserted: InsertedGeneration[] = [];
  const failures = new Map<string | null, Error>();

  const client: ClickHouseInsertClient = {
    insert: async (params): Promise<ClickHouseInsertResult> => {
      for (const value of z.array(z.unknown()).parse(params.values)) {
        const row = insertedRowSchema.parse(value);
        const failure = failures.get(null) ?? failures.get(row.id);
        if (failure) throw failure;

        inserted.push({
          id: row.id,
          slotId: row.properties.settlement.slot_id,
        });
      }

      return { executed: true, query_id: "query", response_headers: {} };
    },
  };

  return {
    inserted,
    writer: createGenerationWriter(client),
    failWith: (error: Error, generationId: string | null = null) => {
      failures.set(generationId, error);
    },
  };
};

export const ingestionTelemetry = (): IngestionTelemetry => ({
  recordIngestedMessages: vi.fn(),
  recordDeletedMessages: vi.fn(),
  recordIngestionBacklog: vi.fn(),
  recordPass: vi.fn(),
});
