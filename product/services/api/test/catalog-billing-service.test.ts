import { describe, expect, it } from "vitest";

import {
  createCatalogBillingService,
  createValkeyServingProjector,
  type ControlDatabase,
  type ServingProjector,
} from "@gradiated/control";

describe("catalog billing service", () => {
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
        quantization: "4-bit",
        tokenizer: "Qwen3",
        input_modalities: [{ type: "text" }],
        output_modalities: [{ type: "text" }],
        pricing: [
          { unit: "input_token", cost: 0 },
          { unit: "output_token", cost: 0 },
        ],
        capacity: [
          { metric: "context_tokens", value: 32_768 },
          { metric: "max_output_tokens", value: 4_096 },
        ],
        passthrough_parameters: {},
        deprecation_at: null,
        is_free: true,
        discount_to_user: 0,
        openrouter: null,
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
