import { describe, expect, it } from "vitest";

import { ModelPropertiesInputSchema } from "@gradiated/contracts";
import {
  createCatalogBillingService,
  type ControlDatabase,
} from "@gradiated/control";

describe("catalog billing service", () => {
  it("caps the normalized output default at a small model's maximum", () => {
    const properties = ModelPropertiesInputSchema.parse({
      description: "Small model.",
      input_modalities: [
        {
          type: "text",
          supported_inputs: {
            max_context_length: { value: 512, unit: "token" },
          },
          pricing: [{ type: "prompt", unit: "token", cost: 0 }],
        },
      ],
      output_modalities: [
        {
          type: "text",
          max_length: { value: 512, unit: "token" },
          pricing: [{ type: "completion", unit: "token", cost: 0 }],
        },
      ],
    });

    expect(properties.output_modalities[0]?.default_length).toEqual({
      value: 512,
      unit: "token",
    });
    expect(() =>
      ModelPropertiesInputSchema.parse({
        ...properties,
        output_modalities: [
          {
            ...properties.output_modalities[0],
            default_length: { value: 513, unit: "token" },
          },
        ],
      }),
    ).toThrow();
  });

  it("persists model-property defaults", async () => {
    const now = new Date("2026-08-18T12:00:00.000Z");
    let inserted: Record<string, unknown> | undefined;

    const database = {
      select: () => ({
        from: () => ({
          where: () => ({
            orderBy: async () => [],
          }),
        }),
      }),
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
    const service = createCatalogBillingService(database);

    const model = await service.upsertModel({
      id: "moonshotai/kimi-k3",
      name: "Kimi K3",
      status: "available",
      properties: {
        description: "Exact Kimi K3 inference.",
        hugging_face_id: "moonshotai/Kimi-K3",
        tokenizer: "Kimi",
        input_modalities: [
          {
            type: "text",
            supported_inputs: {
              max_context_length: { value: 262_144, unit: "token" },
            },
            pricing: [{ type: "prompt", unit: "token", cost: 2_800 }],
          },
        ],
        output_modalities: [
          {
            type: "text",
            max_length: { value: 32_768, unit: "token" },
            supported_parameters: {
              reasoning: { type: "boolean" },
            },
            pricing: [{ type: "completion", unit: "token", cost: 14_000 }],
          },
        ],
      },
    });

    const normalizedProperties = {
      schema_version: 1,
      released_at: null,
      quantization: null,
      passthrough_parameters: {},
      deprecation_date: null,
      input_modalities: [
        {
          supported_inputs: {
            max_prompt_length: { value: 262_144, unit: "token" },
          },
          pricing: [
            { type: "prompt", cost: 2_800 },
            { type: "cached_prompt", cost: 2_800 },
          ],
        },
      ],
      output_modalities: [
        {
          default_length: { value: 1_024, unit: "token" },
          streaming: true,
          pricing: [
            { type: "completion", cost: 14_000 },
            { type: "internal_reasoning", cost: 14_000 },
          ],
        },
      ],
    };
    expect(inserted?.properties).toMatchObject(normalizedProperties);
    expect(model.properties).toMatchObject(normalizedProperties);
  });
});
