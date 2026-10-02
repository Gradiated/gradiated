import { z } from "@hono/zod-openapi";
import {
  ModelSchema,
  ModelPropertiesInputSchema,
  SERVICE_TIER_PRICING_POLICY,
  type Model,
  type ModelPricingEntry,
} from "@gradiated/contracts";
import {
  catalogModel,
  isExternalModelId,
  modelProviderIcon,
} from "@gradiated/contracts/model-catalog";
import { ControlServiceError } from "@gradiated/control";

const nanoRate = z
  .union([z.string().regex(/^\d+(\.\d+)?([eE][+-]?\d+)?$/), z.number()])
  .transform((value) => Number(value) * 1e9)
  .refine(
    (value) =>
      Number.isFinite(value) &&
      value >= 0 &&
      Math.abs(value - Math.round(value)) < 1e-6 &&
      Number.isSafeInteger(Math.round(value)),
  )
  .transform(Math.round);
const rates = z.object({
  prompt: nanoRate,
  completion: nanoRate,
  input_cache_read: nanoRate.optional(),
  input_cache_write: nanoRate.optional(),
});
const providerModel = z.object({
  id: z.string(),
  name: z.string().optional(),
  expiration_date: z.string().nullable().optional(),
  description: z.string(),
  created: z.number().int().nonnegative(),
  context_length: z.number().int().positive(),
  top_provider: z.object({
    max_completion_tokens: z.number().int().positive(),
  }),
  supported_parameters: z.array(z.string()).default([]),
  architecture: z
    .object({
      tokenizer: z.string().nullable().optional(),
      input_modalities: z.array(z.string()).default(["text"]),
      output_modalities: z.array(z.string()).default(["text"]),
    })
    .optional(),
  pricing: rates.extend({
    overrides: z
      .array(
        rates
          .partial()
          .extend({ min_prompt_tokens: z.number().int().nonnegative() }),
      )
      .optional(),
  }),
});
type Rates = { [Key in keyof z.infer<typeof rates>]?: number | undefined };
const inputPrices = (price: Rates): ModelPricingEntry[] => [
  ...(price.prompt === undefined
    ? []
    : [
        { type: "prompt" as const, unit: "token" as const, cost: price.prompt },
      ]),
  ...(price.input_cache_read === undefined
    ? []
    : [
        {
          type: "cached_prompt" as const,
          unit: "token" as const,
          cost: price.input_cache_read,
        },
      ]),
  ...(price.input_cache_write === undefined
    ? []
    : [
        {
          type: "cache_write" as const,
          unit: "token" as const,
          cost: price.input_cache_write,
        },
      ]),
];
const outputPrices = (price: Rates, reasoning: boolean): ModelPricingEntry[] =>
  price.completion === undefined
    ? []
    : [
        { type: "completion", unit: "token", cost: price.completion },
        ...(reasoning
          ? [
              {
                type: "internal_reasoning" as const,
                unit: "token" as const,
                cost: price.completion,
              },
            ]
          : []),
      ];

export const createExternalModelCatalog = (
  send: typeof fetch = fetch,
  now: () => number = Date.now,
) => {
  let cached: { expires: number; data: Model[]; updatedAt: string } | undefined;
  let pending: Promise<Model[]> | undefined;
  let retryAt = 0;
  const unavailable = () =>
    new ControlServiceError(
      "unavailable",
      "External model catalog unavailable.",
    );

  const refresh = async (): Promise<Model[]> => {
    try {
      const response = await send(
        "https://openrouter.ai/api/v1/models?providers=OpenAI,Anthropic",
        {
          signal: AbortSignal.timeout(10000),
          redirect: "error",
        },
      );
      if (!response.ok) throw unavailable();

      const body = z
        .object({ data: z.array(z.unknown()) })
        .parse(await response.json());
      const data: Model[] = [];
      const updatedAt = new Date(now()).toISOString();
      for (const entry of body.data) {
        const parsed = providerModel.safeParse(entry);
        if (!parsed.success) continue;

        const model = parsed.data;
        const modelId = model.id.startsWith("anthropic/")
          ? model.id.replaceAll(".", "-")
          : model.id;
        if (
          !isExternalModelId(modelId) ||
          modelId.endsWith("-high") ||
          (model.expiration_date &&
            Date.parse(model.expiration_date) <= now()) ||
          !model.architecture?.input_modalities.includes("text") ||
          model.architecture.output_modalities.length !== 1 ||
          !model.architecture.output_modalities.includes("text")
        )
          continue;

        const metadata = catalogModel(modelId);
        const reasoning = model.supported_parameters.includes("reasoning");
        const properties = ModelPropertiesInputSchema.parse({
          description: model.description.slice(0, 2000),
          released_at: new Date(model.created * 1000).toISOString(),
          tokenizer: model.architecture?.tokenizer ?? null,
          input_modalities: [
            {
              type: "text",
              supported_inputs: {
                max_context_length: {
                  value: model.context_length,
                  unit: "token",
                },
              },
              pricing: inputPrices(model.pricing),
            },
          ],
          output_modalities: [
            {
              type: "text",
              max_length: {
                value: model.top_provider.max_completion_tokens,
                unit: "token",
              },
              streaming: true,
              supported_parameters: Object.fromEntries(
                model.supported_parameters.map((parameter) => [
                  parameter,
                  { type: "unknown" },
                ]),
              ),
              pricing: outputPrices(model.pricing, reasoning),
            },
          ],
        });
        const result = ModelSchema.safeParse({
          id: modelId,
          name:
            metadata?.displayName ??
            model.name?.replace(/^(OpenAI|Anthropic):\s*/, "") ??
            modelId,
          icon: modelProviderIcon(modelId),
          status: "available",
          properties: {
            ...properties,
            ...(model.pricing.overrides
              ? {
                  pricing_overrides: model.pricing.overrides.map((tier) => ({
                    min_prompt_tokens: tier.min_prompt_tokens,
                    input_pricing: inputPrices(tier),
                    output_pricing: outputPrices(tier, reasoning),
                  })),
                }
              : {}),
          },
          created_at: properties.released_at,
          updated_at: updatedAt,
        });
        if (result.success) data.push(result.data);
      }
      cached = { expires: now() + 5 * 60 * 1000, data, updatedAt };

      return data;
    } catch {
      retryAt = now() + 30 * 1000;
      throw unavailable();
    }
  };

  return async () => {
    if (!cached || cached.expires <= now()) {
      if (retryAt > now()) throw unavailable();

      pending ??= refresh().finally(() => {
        pending = undefined;
      });
      await pending;
    }

    return {
      data: cached!.data,
      next_cursor: null,
      service_tiers: SERVICE_TIER_PRICING_POLICY.map((tier) => ({
        ...tier,
        price_multiplier_numerator: 1,
        price_multiplier_denominator: 1,
        price_change_percent: 0,
      })),
      pricing_source: "openrouter" as const,
      pricing_updated_at: cached!.updatedAt,
    };
  };
};
