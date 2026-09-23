import { describe, expect, it } from "vitest";

import {
  SERVICE_TIER_PRICING_POLICY,
  ServiceTierPricingPolicySchema,
  ServiceTierSchema,
} from "../src/index.js";

describe("SERVICE_TIER_PRICING_POLICY", () => {
  it("prices each service tier exactly once", () => {
    expect(
      SERVICE_TIER_PRICING_POLICY.map(
        ({ service_tier }) => service_tier,
      ).sort(),
    ).toEqual([...ServiceTierSchema.options].sort());
  });

  it.each(SERVICE_TIER_PRICING_POLICY)(
    "satisfies the schema for $service_tier",
    (policy) => {
      expect(ServiceTierPricingPolicySchema.parse(policy)).toEqual(policy);
    },
  );
});

describe("ServiceTierPricingPolicySchema", () => {
  it("rejects a percent that disagrees with the multiplier", () => {
    const result = ServiceTierPricingPolicySchema.safeParse({
      service_tier: "fast",
      price_multiplier_numerator: 3,
      price_multiplier_denominator: 2,
      price_change_percent: 40,
    });

    expect(result.error?.issues).toEqual([
      expect.objectContaining({ path: ["price_change_percent"] }),
    ]);
  });
});
