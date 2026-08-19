import { describe, expect, it } from "vitest";

import { ModelPropertiesInputSchema } from "@gradiated/contracts";
import {
  createCatalogBillingService,
  createValkeyServingProjector,
  type ControlDatabase,
  type ServingProjector,
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

  it("persists and projects model-property defaults", async () => {
    const now = new Date("2026-08-18T12:00:00.000Z");
    let inserted: Record<string, unknown> | undefined;
    let projected: Parameters<ServingProjector["projectModel"]>[0] | undefined;

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
    expect(projected?.properties).toMatchObject(normalizedProperties);
    expect(projected?.deployments).toEqual([]);
  });

  it("projects model deployments inside the existing GatewayModel value", async () => {
    const writes = new Map<string, string>();
    const modelIds = new Set<string>();
    const projector = createValkeyServingProjector({
      set: async (key, value) => writes.set(key, value),
      sAdd: async (_key, value) => modelIds.add(value),
      hSet: async () => undefined,
      eval: async () => undefined,
    });

    await projector.projectModel({
      id: "mlx-community/qwen3-0.6b-4bit",
      name: "Qwen3 0.6B 4-bit",
      status: "available",
      properties: {
        schema_version: 1,
        description: "Local model.",
        released_at: null,
        hugging_face_id: "mlx-community/Qwen3-0.6B-4bit",
        quantization: "int4",
        tokenizer: "Qwen3",
        input_modalities: [
          {
            type: "text",
            supported_inputs: {
              max_context_length: { value: 32_768, unit: "token" },
              max_prompt_length: { value: 32_768, unit: "token" },
            },
            pricing: [
              { type: "prompt", unit: "token", cost: 0 },
              { type: "cached_prompt", unit: "token", cost: 0 },
            ],
          },
        ],
        output_modalities: [
          {
            type: "text",
            max_length: { value: 4_096, unit: "token" },
            default_length: { value: 1_024, unit: "token" },
            streaming: true,
            supported_parameters: {},
            pricing: [{ type: "completion", unit: "token", cost: 0 }],
          },
        ],
        passthrough_parameters: {},
        deprecation_date: null,
      },
      deployments: [
        {
          id: "0198c36f-9b6a-7000-8000-000000000004",
          status: "available",
          serviceUrl: "http://127.0.0.1:30000",
          release: {
            schema_version: 1,
            runtime_revision: "runtime-revision",
            model_path: "model-path",
            model_revision: "model-revision",
            tokenizer_path: "tokenizer-path",
            tokenizer_revision: "tokenizer-revision",
          },
        },
        {
          id: "0198c36f-9b6a-7000-8000-000000000005",
          status: "available",
          serviceUrl: "http://127.0.0.1:30001",
          release: {
            schema_version: 1,
            runtime_revision: "second-runtime-revision",
            model_path: "model-path",
            model_revision: "model-revision",
            tokenizer_path: "tokenizer-path",
            tokenizer_revision: "tokenizer-revision",
          },
        },
      ],
    });

    expect(modelIds).toContain("mlx-community/qwen3-0.6b-4bit");
    expect(
      JSON.parse(writes.get("model:mlx-community/qwen3-0.6b-4bit") ?? ""),
    ).toMatchObject({
      deployments: [
        {
          id: "0198c36f-9b6a-7000-8000-000000000004",
          service_url: "http://127.0.0.1:30000",
          release: { schema_version: 1 },
        },
        {
          id: "0198c36f-9b6a-7000-8000-000000000005",
          service_url: "http://127.0.0.1:30001",
          release: { schema_version: 1 },
        },
      ],
    });
  });
});
