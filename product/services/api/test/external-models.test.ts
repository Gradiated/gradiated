import { expect, it, vi } from "vitest";
import { ModelListSchema, ExternalModelListSchema } from "@gradiated/contracts";
import { createExternalModelCatalog } from "../src/catalog/external-models.js";
import { createTestApp, modelRecord, sessionStoreDown } from "./support.js";

const provider = {
  id: "openai/gpt-6.1-sol",
  name: "OpenAI: GPT-6.1 Sol",
  architecture: { input_modalities: ["text"], output_modalities: ["text"] },
  description: "Synthetic provider model.",
  created: 1750000000,
  context_length: 1000000,
  top_provider: { max_completion_tokens: 128000 },
  supported_parameters: ["reasoning", "temperature"],
  pricing: {
    prompt: "0.000002",
    completion: "0.00001",
    input_cache_read: "0.0000001",
    overrides: [
      { min_prompt_tokens: 272000, prompt: "0.000004", completion: "0.000015" },
    ],
  },
};
const feed = (models: unknown[] = [provider]) =>
  new Response(JSON.stringify({ data: models }));

it.each([
  ["openai/gpt-6.1-sol-pro", "openai/gpt-6.1-sol-pro"],
  ["openai/gpt-6-astra-pro", "openai/gpt-6-astra-pro"],
  ["openai/gpt-6-sol-pro", "openai/gpt-6-sol-pro"],
  ["openai/gpt-6-luna-pro", "openai/gpt-6-luna-pro"],
  ["anthropic/claude-fable-5.1", "anthropic/claude-fable-5-1"],
  ["anthropic/claude-opus-5.5", "anthropic/claude-opus-5-5"],
  ["anthropic/claude-sonnet-5.5", "anthropic/claude-sonnet-5-5"],
  ["anthropic/claude-haiku-5.5", "anthropic/claude-haiku-5-5"],
])(
  "matches OpenRouter's %s while preserving the canonical %s ID",
  async (sourceId, id) => {
    const send = vi
      .fn<typeof fetch>()
      .mockImplementation(async () => feed([{ ...provider, id: sourceId }]));
    expect((await createExternalModelCatalog(send)()).data[0]?.id).toBe(id);
  },
);

it("loads plain models without touching the external service or making outbound requests", async () => {
  const send = vi.fn<typeof fetch>().mockRejectedValue(new Error("offline"));
  const externalModels = vi.fn(createExternalModelCatalog(send));
  const app = createTestApp({
    externalModels,
    services: { catalogBilling: { listModels: async () => [modelRecord] } },
  });
  for (const path of ["/api/v1/models", "/api/v1/models?external=false"]) {
    const response = await app.request(path);
    expect(response.status).toBe(200);
    expect(ModelListSchema.parse(await response.json()).data[0]!.id).toBe(
      modelRecord.id,
    );
  }
  expect(externalModels).not.toHaveBeenCalled();
  expect(send).not.toHaveBeenCalled();
});

it("preserves the legacy external pricing feed without changing the hosted catalog", async () => {
  const send = vi.fn<typeof fetch>().mockImplementation(async () => feed());
  const listHosted = vi.fn().mockResolvedValue([modelRecord]);
  const app = createTestApp({
    auth: sessionStoreDown,
    externalModels: createExternalModelCatalog(send),
    services: { catalogBilling: { listModels: listHosted } },
  });
  const response = await app.request("/api/v1/models?external=true");
  expect(response.status).toBe(200);
  const external = ExternalModelListSchema.parse(await response.json());
  expect(external.data[0]?.properties).not.toHaveProperty("type");
  expect(external.data[0]).toMatchObject({
    id: provider.id,
    name: "GPT-6.1 Sol",
    icon: "/model-providers/openai.svg",
    properties: {
      input_modalities: [
        {
          pricing: [
            { type: "prompt", cost: 2000 },
            { type: "cached_prompt", cost: 100 },
          ],
        },
      ],
      output_modalities: [
        {
          pricing: [
            { type: "completion", cost: 10000 },
            { type: "internal_reasoning", cost: 10000 },
          ],
        },
      ],
      pricing_overrides: [
        {
          min_prompt_tokens: 272000,
          input_pricing: [{ type: "prompt", cost: 4000 }],
          output_pricing: [
            { type: "completion", cost: 15000 },
            { type: "internal_reasoning", cost: 15000 },
          ],
        },
      ],
    },
  });
  expect(listHosted).not.toHaveBeenCalled();
  expect(
    external.service_tiers.every((tier) => tier.price_change_percent === 0),
  ).toBe(true);
  for (const path of ["/api/v1/models", "/api/v1/models?external=false"]) {
    const hosted = ModelListSchema.parse(
      await (await app.request(path)).json(),
    );
    expect(hosted.data[0]!.id).toBe(modelRecord.id);
  }
  expect(send).toHaveBeenCalledTimes(1);
  expect((await app.request("/api/v1/models?external=invalid")).status).toBe(
    422,
  );
});

it("shares concurrent fetches and refreshes the API memory cache after five minutes", async () => {
  let now = Date.parse("2026-10-02T12:00:00Z");
  const send = vi.fn<typeof fetch>().mockImplementation(async () => feed());
  const load = createExternalModelCatalog(send, () => now);
  await Promise.all([load(), load(), load()]);
  expect(send).toHaveBeenCalledTimes(1);
  now += 5 * 60 * 1000 - 1;
  await load();
  expect(send).toHaveBeenCalledTimes(1);
  now += 1;
  const catalog = await load();
  expect(send).toHaveBeenCalledTimes(2);
  expect(catalog.pricing_updated_at).toBe("2026-10-02T12:05:00.000Z");
});

it.each([null, "", "-0.01", "not-a-price"])(
  "omits malformed pricing (%s) instead of advertising zero",
  async (prompt) => {
    const send = vi
      .fn<typeof fetch>()
      .mockImplementation(async () =>
        feed([{ ...provider, pricing: { ...provider.pricing, prompt } }]),
      );
    expect((await createExternalModelCatalog(send)()).data).toEqual([]);
  },
);

it("allows published free rates and omits models outside the supported providers", async () => {
  const send = vi.fn<typeof fetch>().mockImplementation(async () =>
    feed([
      { ...provider, pricing: { prompt: "0", completion: "0" } },
      { ...provider, id: "google/gemini" },
    ]),
  );
  const catalog = await createExternalModelCatalog(send)();
  expect(catalog.data).toHaveLength(1);
  expect(
    catalog.data[0]!.properties.input_modalities[0]!.pricing[0]!.cost,
  ).toBe(0);
});

it("returns 503 for a feed outage and suppresses repeat fetches for 30 seconds", async () => {
  let now = Date.parse("2026-10-02T12:00:00Z");
  const send = vi.fn<typeof fetch>().mockRejectedValue(new Error("offline"));
  const app = createTestApp({
    externalModels: createExternalModelCatalog(send, () => now),
  });
  expect((await app.request("/api/v1/models?external=true")).status).toBe(503);
  expect((await app.request("/api/v1/models?external=true")).status).toBe(503);
  expect(send).toHaveBeenCalledTimes(1);
  now += 30000;
  expect((await app.request("/api/v1/models?external=true")).status).toBe(503);
  expect(send).toHaveBeenCalledTimes(2);
});

it("discovers new text models and excludes expired, non-text, and routing variants", async () => {
  const send = vi.fn<typeof fetch>().mockImplementation(async () =>
    feed([
      { ...provider, id: "openai/gpt-4.1-mini", name: "OpenAI: GPT-4.1 Mini" },
      { ...provider, id: "openai/expired", expiration_date: "2020-01-01" },
      {
        ...provider,
        id: "openai/image",
        architecture: {
          input_modalities: ["text"],
          output_modalities: ["image"],
        },
      },
      { ...provider, id: "openai/gpt-4.1:batch" },
      { ...provider, id: "openai/o4-mini-high" },
    ]),
  );
  const result = await createExternalModelCatalog(send)();
  expect(
    result.data.map((model) => ({
      id: model.id,
      name: model.name,
      icon: model.icon,
    })),
  ).toEqual([
    {
      id: "openai/gpt-4.1-mini",
      name: "GPT-4.1 Mini",
      icon: "/model-providers/openai.svg",
    },
  ]);
  expect(send.mock.calls[0]?.[0]).toBe(
    "https://openrouter.ai/api/v1/models?providers=OpenAI,Anthropic",
  );
});
