import { z } from "@hono/zod-openapi";

export const ServiceTierSchema = z
  .enum(["flex", "default", "fast"])
  .openapi("ServiceTier");

export const ServiceTierPricingPolicySchema = z
  .strictObject({
    service_tier: ServiceTierSchema,
    price_multiplier_numerator: z.number().int().positive(),
    price_multiplier_denominator: z.number().int().positive(),
    price_change_percent: z.number().int(),
  })
  .openapi("ServiceTierPricingPolicy");

export const SERVICE_TIER_PRICING_POLICY = [
  {
    service_tier: "flex",
    price_multiplier_numerator: 7,
    price_multiplier_denominator: 10,
    price_change_percent: -30,
  },
  {
    service_tier: "default",
    price_multiplier_numerator: 1,
    price_multiplier_denominator: 1,
    price_change_percent: 0,
  },
  {
    service_tier: "fast",
    price_multiplier_numerator: 3,
    price_multiplier_denominator: 2,
    price_change_percent: 50,
  },
] as const satisfies ReadonlyArray<ServiceTierPricingPolicy>;

export type ServiceTier = z.infer<typeof ServiceTierSchema>;
export type ServiceTierPricingPolicy = z.infer<
  typeof ServiceTierPricingPolicySchema
>;
