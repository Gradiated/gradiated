import { z } from "zod";
import { ModelListSchema, type ModelProperties } from "@gradiated/contracts";
import type { CatalogService } from "@gradiated/control";

const rate = z.number().finite().nonnegative();
const ratesSchema = z.object({
  prompt: rate,
  completion: rate,
  input_cache_read: rate.optional(),
  input_cache_write: rate.optional(),
});
const evaluationPriceSchema = z.object({
  model_id: z.string(),
  source: z.enum(["hosted_catalog", "openrouter"]),
  rates: ratesSchema.extend({
    overrides: z
      .array(
        ratesSchema
          .partial()
          .extend({ min_prompt_tokens: z.number().int().nonnegative() }),
      )
      .optional(),
  }),
});
export const evaluationPricingSchema = z.object({
  captured_at: z.iso.datetime(),
  fine_tuned: evaluationPriceSchema.nullable(),
  comparison: evaluationPriceSchema.nullable(),
});
export type EvaluationPrice = z.infer<typeof evaluationPriceSchema>;
export type EvaluationPricing = z.infer<typeof evaluationPricingSchema>;

const tokenRates = (
  input: ModelProperties["input_modalities"][number]["pricing"],
  output: ModelProperties["output_modalities"][number]["pricing"],
) => {
  const prompt = input.find((entry) => entry.type === "prompt");
  const completion = output.find((entry) => entry.type === "completion");
  const read = input.find((entry) => entry.type === "cached_prompt");
  const write = input.find((entry) => entry.type === "cache_write");

  return {
    ...(prompt ? { prompt: prompt.cost / 1e9 } : {}),
    ...(completion ? { completion: completion.cost / 1e9 } : {}),
    ...(read ? { input_cache_read: read.cost / 1e9 } : {}),
    ...(write ? { input_cache_write: write.cost / 1e9 } : {}),
  };
};
const modelPrice = (
  id: string,
  properties: ModelProperties,
  source: EvaluationPrice["source"],
): EvaluationPrice =>
  evaluationPriceSchema.parse({
    model_id: id,
    source,
    rates: {
      ...tokenRates(
        properties.input_modalities[0]!.pricing,
        properties.output_modalities[0]!.pricing,
      ),
      ...(properties.pricing_overrides
        ? {
            overrides: properties.pricing_overrides.map((tier) => ({
              min_prompt_tokens: tier.min_prompt_tokens,
              ...tokenRates(tier.input_pricing, tier.output_pricing),
            })),
          }
        : {}),
    },
  });

export const createEvaluationPricing = (
  catalog: Pick<CatalogService, "listModels">,
  send: typeof fetch = fetch,
) => {
  const externalPrices = async (signal: AbortSignal) => {
    const prices = new Map<string, EvaluationPrice>();
    try {
      const response = await send(
        "https://api.gradiated.com/api/v1/models?external=true",
        {
          signal: AbortSignal.any([signal, AbortSignal.timeout(10000)]),
          redirect: "error",
        },
      );
      if (!response.ok) return prices;

      const external = ModelListSchema.parse(await response.json());
      for (const model of external.data) {
        if (model.status === "available")
          prices.set(
            model.id,
            modelPrice(model.id, model.properties, "openrouter"),
          );
      }
    } catch {
      signal.throwIfAborted();
    }

    return prices;
  };

  return async (
    baseModelId: string,
    comparisonModelId: string,
    signal: AbortSignal,
  ): Promise<EvaluationPricing> => {
    const ids = [baseModelId, comparisonModelId];
    const isExternal = (id: string) =>
      id.startsWith("openai/") || id.startsWith("anthropic/");
    const external = ids.some(isExternal)
      ? await externalPrices(signal)
      : new Map<string, EvaluationPrice>();
    const hosted = ids.some((id) => !isExternal(id))
      ? await catalog.listModels()
      : [];
    const price = (id: string): EvaluationPrice | null => {
      if (isExternal(id)) return external.get(id) ?? null;

      const model = hosted.find(
        (model) => model.id === id && model.status === "available",
      );

      return model ? modelPrice(id, model.properties, "hosted_catalog") : null;
    };

    return {
      captured_at: new Date().toISOString(),
      fine_tuned: price(baseModelId),
      comparison: price(comparisonModelId),
    };
  };
};
