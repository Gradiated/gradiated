import { expect, it, vi } from "vitest";
import {
  ModelPropertiesInputSchema,
  SERVICE_TIER_PRICING_POLICY,
} from "@gradiated/contracts";
import type { CatalogService } from "@gradiated/control";
import { createGlm53FlashModelConfiguration } from "../../../packages/control/src/catalog/models/glm-5-3-flash.js";
import {
  createEvaluationPricing,
  type EvaluationPricing,
} from "../src/training/evaluation-pricing.js";
import {
  estimateTokenCost,
  predictionsSchema,
  pricePredictions,
} from "../src/training/evaluation.js";

const signal = new AbortController().signal;
const catalog = {
  listModels: vi
    .fn()
    .mockResolvedValue([
      { ...createGlm53FlashModelConfiguration(), status: "available" },
    ]),
} as Pick<CatalogService, "listModels">;
const provider = {
  id: "openai/gpt-6.1-sol",
  name: "GPT-6.1 Sol",
  status: "available",
  created_at: "2026-10-02T12:00:00Z",
  updated_at: "2026-10-02T12:00:00Z",
  properties: ModelPropertiesInputSchema.parse({
    description: "Synthetic provider model.",
    input_modalities: [
      {
        type: "text",
        supported_inputs: {
          max_context_length: { value: 1000000, unit: "token" },
        },
        pricing: [
          { type: "prompt", unit: "token", cost: 2000 },
          { type: "cached_prompt", unit: "token", cost: 100 },
        ],
      },
    ],
    output_modalities: [
      {
        type: "text",
        max_length: { value: 128000, unit: "token" },
        pricing: [{ type: "completion", unit: "token", cost: 10000 }],
      },
    ],
  }),
};
const pricing: EvaluationPricing = {
  captured_at: "2026-10-02T12:00:00Z",
  fine_tuned: {
    model_id: "z-ai/glm-5.3-flash",
    source: "hosted_catalog",
    rates: { prompt: 75 / 1e9, completion: 250 / 1e9 },
  },
  comparison: {
    model_id: provider.id,
    source: "openrouter",
    rates: {
      prompt: 2000 / 1e9,
      completion: 10000 / 1e9,
      input_cache_read: 100 / 1e9,
    },
  },
};
const rows = (
  usage = { input_tokens: 100, output_tokens: 40, cached_input_tokens: 20 },
) =>
  predictionsSchema.parse([
    {
      id: "example",
      group: "group",
      judgment: "A",
      fine_tuned_first: true,
      fine_tuned: {
        text: "fine",
        tokens: 10,
        seconds: 1,
        usage: { input_tokens: 100, output_tokens: 10 },
      },
      comparison: { text: "comparison", tokens: 20, seconds: 1, usage },
    },
  ]);

it("loads provider prices from the API and uses our hosted rates without a worker cache", async () => {
  const send = vi.fn<typeof fetch>().mockImplementation(
    async () =>
      new Response(
        JSON.stringify({
          data: [provider],
          next_cursor: null,
          service_tiers: SERVICE_TIER_PRICING_POLICY,
          pricing_source: "openrouter",
          pricing_updated_at: "2026-10-02T12:00:00Z",
        }),
      ),
  );
  const load = createEvaluationPricing(catalog, send);
  const result = await load("z-ai/glm-5.3-flash", provider.id, signal);
  expect(result.fine_tuned).toMatchObject({
    model_id: "z-ai/glm-5.3-flash",
    source: "hosted_catalog",
    rates: { prompt: 150 / 1e9, completion: 500 / 1e9 },
  });
  expect(result.comparison?.rates.prompt).toBe(0.000002);
  await load("z-ai/glm-5.3-flash", provider.id, signal);
  expect(send).toHaveBeenCalledTimes(2);
  expect(send.mock.calls[0]![0]).toBe(
    "https://api.gradiated.com/api/v1/models?external=true",
  );
  expect(send.mock.calls[0]![1]).not.toHaveProperty("headers");
  expect(
    (await load("z-ai/glm-5.3-flash", "openai/unknown", signal)).comparison,
  ).toBeNull();
});

it("keeps missing provider prices unknown when the feed fails", async () => {
  const send = vi.fn<typeof fetch>().mockRejectedValue(new Error("offline"));
  const result = await createEvaluationPricing(catalog, send)(
    "z-ai/glm-5.3-flash",
    provider.id,
    signal,
  );
  expect(result.fine_tuned).not.toBeNull();
  expect(result.comparison).toBeNull();
});

it("includes input, cached input and billable output, independently of visible-token timing", () => {
  expect(estimateTokenCost(rows(), pricing)).toEqual({
    fine_tuned: 10000,
    comparison: 562000,
  });
});

it("uses long-context price overrides at the exact threshold", () => {
  const longPricing = {
    ...pricing,
    comparison: {
      ...pricing.comparison!,
      rates: {
        prompt: 0.000002,
        completion: 0.00001,
        overrides: [
          { min_prompt_tokens: 272000, prompt: 0.000004, completion: 0.000015 },
        ],
      },
    },
  };
  expect(
    estimateTokenCost(
      rows({ input_tokens: 272000, output_tokens: 40, cached_input_tokens: 0 }),
      longPricing,
    )?.comparison,
  ).toBe(1088600000);
  expect(
    estimateTokenCost(
      rows({ input_tokens: 271999, output_tokens: 40, cached_input_tokens: 0 }),
      longPricing,
    )?.comparison,
  ).toBe(544398000);
});

it("keeps legacy or incompletely priced usage unknown and allows explicitly free rates", () => {
  const legacy = rows();
  delete legacy[0]!.fine_tuned.usage;
  expect(estimateTokenCost(legacy, pricing)).toBeNull();
  expect(
    estimateTokenCost(rows(), { ...pricing, comparison: null }),
  ).toBeNull();
  expect(
    estimateTokenCost(
      rows({ input_tokens: 10, output_tokens: 5, cached_input_tokens: 11 }),
      pricing,
    ),
  ).toBeNull();
  expect(
    estimateTokenCost(
      rows({ input_tokens: 10, output_tokens: 5, cached_input_tokens: 0 }),
      {
        ...pricing,
        fine_tuned: {
          ...pricing.fine_tuned!,
          rates: { prompt: 0, completion: 0 },
        },
      },
    )?.fine_tuned,
  ).toBe(0);
});

it("saves each arm's cost while keeping legacy and missing rates unknown", () => {
  const priced = predictionsSchema.parse(
    pricePredictions(rows(), pricing, false),
  );
  expect(priced[0]!.fine_tuned.cost_nano_usd).toBe(10000);
  expect(priced[0]!.comparison.cost_nano_usd).toBe(562000);
  expect(rows()[0]!.fine_tuned).not.toHaveProperty("cost_nano_usd");

  const legacy = rows();
  delete legacy[0]!.fine_tuned.usage;
  const partial = pricePredictions(legacy, pricing, false);
  expect(partial[0]!.fine_tuned).not.toHaveProperty("cost_nano_usd");
  expect(partial[0]!.comparison.cost_nano_usd).toBe(562000);
  expect(
    pricePredictions(rows(), undefined, false)[0]!.comparison,
  ).not.toHaveProperty("cost_nano_usd");
});

it("saves zero and placeholder costs rather than treating them as missing", () => {
  const free = {
    ...pricing,
    fine_tuned: { ...pricing.fine_tuned!, rates: { prompt: 0, completion: 0 } },
  };
  expect(
    pricePredictions(rows(), free, false)[0]!.fine_tuned.cost_nano_usd,
  ).toBe(0);
  const placeholder = pricePredictions(rows(), undefined, true);
  expect(placeholder[0]!.fine_tuned.cost_nano_usd).toBe(1000);
  expect(placeholder[0]!.comparison.cost_nano_usd).toBe(2000);
});
