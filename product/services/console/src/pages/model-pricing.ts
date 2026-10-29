import type { Model, ServiceTierPricingPolicy } from "@/api/queries";
import { NANO_USD_PER_USD } from "@/lib/money";

type Modalities = Model["properties"];
type PriceType =
  | Modalities["input_modalities"][number]["pricing"][number]["type"]
  | Modalities["output_modalities"][number]["pricing"][number]["type"];

const PRICE_ROWS = [
  { type: "prompt", label: "Input" },
  { type: "cached_prompt", label: "Cached input" },
  { type: "cache_write", label: "Cache write" },
  { type: "completion", label: "Output" },
  { type: "internal_reasoning", label: "Reasoning output" },
] as const satisfies ReadonlyArray<{ type: PriceType; label: string }>;

const TOKENS_PER_MILLION = 1_000_000;

export const usdPerMillionTokens = (nanoUsdPerToken: number): number =>
  (nanoUsdPerToken * TOKENS_PER_MILLION) / Number(NANO_USD_PER_USD);

const defaultPrice = (model: Model, type: PriceType): number | undefined => {
  const entries = [
    ...(model.properties.input_modalities[0]?.pricing ?? []),
    ...(model.properties.output_modalities[0]?.pricing ?? []),
  ];

  return entries.find((entry) => entry.type === type)?.cost;
};

const tierPrice = (
  defaultNanoUsd: number,
  policy: ServiceTierPricingPolicy,
): number =>
  Number(
    (BigInt(defaultNanoUsd) * BigInt(policy.price_multiplier_numerator)) /
      BigInt(policy.price_multiplier_denominator),
  );

interface TierPriceRow {
  type: PriceType;
  label: string;
  prices: { tier: ServiceTierPricingPolicy["service_tier"]; usd: number }[];
}

export const tierPriceRows = (
  model: Model,
  policies: readonly ServiceTierPricingPolicy[],
): TierPriceRow[] =>
  PRICE_ROWS.flatMap(({ type, label }) => {
    const price = defaultPrice(model, type);
    if (price === undefined) return [];

    return [
      {
        type,
        label,
        prices: policies.map((policy) => ({
          tier: policy.service_tier,
          usd: usdPerMillionTokens(tierPrice(price, policy)),
        })),
      },
    ];
  });

export const tierLabel = (policy: ServiceTierPricingPolicy): string => {
  const name =
    policy.service_tier.charAt(0).toUpperCase() + policy.service_tier.slice(1);
  if (policy.price_change_percent === 0) return name;

  const sign = policy.price_change_percent > 0 ? "+" : "";

  return `${name} (${sign}${policy.price_change_percent}%)`;
};
