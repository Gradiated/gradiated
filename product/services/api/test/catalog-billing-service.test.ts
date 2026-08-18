import { describe, expect, it } from "vitest";

import {
  createCatalogBillingService,
  type ControlDatabase,
  type ServingProjector,
} from "@gradiated/control";

describe("catalog billing service", () => {
  it("persists and projects model-property defaults", async () => {
    const now = new Date("2026-08-18T12:00:00.000Z");
    let inserted: Record<string, unknown> | undefined;
    let projected: Parameters<ServingProjector["projectModel"]>[0] | undefined;

    const database = {
      insert: () => ({
        values: (values: Record<string, unknown>) => {
          inserted = values;
          return {
            onConflictDoUpdate: () => ({
              returning: async () => [
                {
                  ...values,
                  createdAt: now,
                  updatedAt: now,
                },
              ],
            }),
          };
        },
      }),
    } as unknown as ControlDatabase;
    const projector = {
      projectModel: async (model) => {
        projected = model;
      },
    } as ServingProjector;
    const service = createCatalogBillingService(database, projector);

    const model = await service.upsertModel({
      id: "moonshotai/kimi-k3",
      name: "Kimi K3",
      status: "available",
      properties: {
        schema_version: 1,
        description: "Exact Kimi K3 inference.",
        released_at: null,
        hugging_face_id: "moonshotai/Kimi-K3",
        quantization: null,
        tokenizer: "Kimi",
        input_modalities: [{ type: "text" }],
        output_modalities: [{ type: "text" }],
        pricing: [
          { unit: "input_token", cost: 2_800 },
          { unit: "output_token", cost: 14_000 },
        ],
        capacity: [
          { metric: "context_tokens", value: 262_144 },
          { metric: "max_output_tokens", value: 32_768 },
        ],
        passthrough_parameters: {
          stream: { type: "boolean" },
        },
        deprecation_at: null,
        openrouter: null,
      },
    });

    expect(inserted?.properties).toMatchObject({
      is_free: false,
      discount_to_user: 0,
    });
    expect(model.properties).toMatchObject({
      is_free: false,
      discount_to_user: 0,
    });
    expect(projected?.properties).toMatchObject({
      is_free: false,
      discount_to_user: 0,
    });
  });
});
