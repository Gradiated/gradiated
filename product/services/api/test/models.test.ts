import { describe, expect, it } from "vitest";

import { createTestApp, modelRecord, sessionStoreDown } from "./support.js";

describe("model catalog route", () => {
  it("lists the advertised exact models without a session", async () => {
    const app = createTestApp({
      services: { catalogBilling: { listModels: async () => [modelRecord] } },
    });

    const response = await app.request("/api/v1/models");

    expect(response.status).toBe(200);
    expect(response.headers.get("Cache-Control")).toBe(
      "public, max-age=15, s-maxage=15, stale-while-revalidate=15",
    );
    await expect(response.json()).resolves.toMatchObject({
      data: [
        {
          id: "moonshotai/kimi-k3",
          status: "available",
          properties: {
            input_modalities: [{ pricing: [{ cost: 2_800 }, { cost: 2_800 }] }],
            output_modalities: [{ pricing: [{ cost: 14_000 }] }],
          },
        },
      ],
      service_tiers: [
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
      ],
    });
  });

  it("serves the catalog while the session store is unreachable", async () => {
    const app = createTestApp({
      auth: sessionStoreDown,
      services: { catalogBilling: { listModels: async () => [modelRecord] } },
    });

    const response = await app.request("/api/v1/models");

    expect(response.status).toBe(200);
  });

  it("leaves retired models out of the catalog", async () => {
    const app = createTestApp({
      services: {
        catalogBilling: {
          listModels: async () => [
            modelRecord,
            { ...modelRecord, id: "retired/model", status: "retired" },
          ],
        },
      },
    });

    const response = await app.request("/api/v1/models");

    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toMatchObject({
      data: [{ id: modelRecord.id }],
    });
  });
});
