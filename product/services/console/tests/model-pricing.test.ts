import { describe, expect, it } from "vitest";

import type { Model, ServiceTierPricingPolicy } from "@/api/queries";
import { tierPriceRows, usdPerMillionTokens } from "@/pages/model-pricing";

const chatModels = (models: readonly Model[]) =>
  models.filter((model) => model.properties.type === "chat");

const policy = (
  service_tier: ServiceTierPricingPolicy["service_tier"],
  numerator: number,
  denominator: number,
): ServiceTierPricingPolicy => ({
  service_tier,
  price_multiplier_numerator: numerator,
  price_multiplier_denominator: denominator,
  price_change_percent: Math.round((numerator / denominator - 1) * 100),
});

const model = {
  id: "google/gemma-4-31b-it",
  name: "Gemma 4 31B",
  status: "available",
  created_at: "2026-08-16T12:00:00.000Z",
  updated_at: "2026-08-16T12:00:00.000Z",
  properties: {
    schema_version: 1,
    type: "chat",
    description: "",
    released_at: null,
    hugging_face_id: null,
    quantization: null,
    tokenizer: null,
    deprecation_date: null,
    passthrough_parameters: {},
    input_modalities: [
      {
        type: "text",
        supported_inputs: {
          max_context_length: { value: 128_000, unit: "token" },
          max_prompt_length: { value: 120_000, unit: "token" },
        },
        pricing: [
          { type: "prompt", unit: "token", cost: 200 },
          { type: "cached_prompt", unit: "token", cost: 50 },
        ],
      },
    ],
    output_modalities: [
      {
        type: "text",
        max_length: { value: 8_192, unit: "token" },
        default_length: { value: 1_024, unit: "token" },
        streaming: true,
        supported_parameters: {},
        pricing: [{ type: "completion", unit: "token", cost: 600 }],
      },
    ],
  },
} satisfies Model;

describe("usdPerMillionTokens", () => {
  it("converts nano-USD per token to USD per million tokens", () => {
    expect(usdPerMillionTokens(200)).toBe(0.2);
    expect(usdPerMillionTokens(0)).toBe(0);
  });
});

describe("tierPriceRows", () => {
  it("supports the documented chat filter across generated response variants", () => {
    const { type: _type, ...properties } = model.properties;
    const legacy: Model = {
      ...model,
      id: "external/legacy-model",
      properties,
    };

    expect(chatModels([model, legacy])).toEqual([model]);
  });
  it("prices each listed token type for every tier in order", () => {
    const rows = tierPriceRows(model, [
      policy("flex", 1, 2),
      policy("default", 1, 1),
      policy("fast", 3, 2),
    ]);

    expect(rows).toEqual([
      {
        type: "prompt",
        label: "Input",
        prices: [
          { tier: "flex", usd: 0.1 },
          { tier: "default", usd: 0.2 },
          { tier: "fast", usd: 0.3 },
        ],
      },
      {
        type: "cached_prompt",
        label: "Cached input",
        prices: [
          { tier: "flex", usd: 0.025 },
          { tier: "default", usd: 0.05 },
          { tier: "fast", usd: 0.075 },
        ],
      },
      {
        type: "completion",
        label: "Output",
        prices: [
          { tier: "flex", usd: 0.3 },
          { tier: "default", usd: 0.6 },
          { tier: "fast", usd: 0.9 },
        ],
      },
    ]);
  });
});
