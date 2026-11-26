import { describe, expect, it } from "vitest";
import { createOpenApiDocument } from "../src/openapi.js";

import {
  createTestApp,
  modelRecord,
  organizationModelRecord,
  sessionStoreDown,
} from "./support.js";

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
            type: "chat",
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

  it("lists each row's stored type without mutating its properties", async () => {
    const decisionRecord = {
      ...modelRecord,
      id: "jaredpalmer/kev-9b",
      type: "decision" as const,
    };
    const app = createTestApp({
      services: {
        catalogBilling: {
          listModels: async () => [modelRecord, decisionRecord],
        },
      },
    });

    const response = await app.request("/api/v1/models");
    const body = await response.json();

    expect(response.status).toBe(200);
    expect(
      body.data.filter(
        (model: { properties: { type: string } }) =>
          model.properties.type === "chat",
      ),
    ).toMatchObject([{ id: modelRecord.id }]);
    expect(body.data[1].properties.type).toBe("decision");
    expect(decisionRecord.properties).not.toHaveProperty("type");
    expect(modelRecord.properties).not.toHaveProperty("type");
  });

  it("marks training-only bases as unavailable for serving", async () => {
    const trainingRecord = { ...modelRecord, id: "Qwen/Qwen3-8B" };
    const app = createTestApp({
      services: {
        catalogBilling: {
          listModels: async () => [modelRecord, trainingRecord],
        },
      },
    });

    const response = await app.request("/api/v1/models");
    const body = await response.json();

    expect(body.data[0].properties.supported_uses).toEqual(["serving"]);
    expect(body.data[1].properties.supported_uses).toEqual(["training"]);
  });

  it("requires model type in the generated public response schema", () => {
    const document = createOpenApiDocument();

    expect(document.components?.schemas?.ModelProperties).toMatchObject({
      required: expect.arrayContaining(["type", "supported_uses"]),
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

  it("hides legacy Dealign IDs while they remain available for cutover", async () => {
    const renamed = "glm-5.3-flash-cyber";
    const app = createTestApp({
      services: {
        catalogBilling: {
          listModels: async () => [
            { ...modelRecord, id: renamed },
            {
              ...modelRecord,
              id: "dealignai/glm-5.3-flash-uncensored",
              status: "available",
            },
            {
              ...modelRecord,
              id: "dealignai/glm-5.3-flash-uncensored-nvfp4",
              status: "available",
            },
          ],
        },
      },
    });

    const response = await app.request("/api/v1/models");

    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toMatchObject({
      data: [{ id: renamed }],
    });
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

  it("never publishes an organization's own model", async () => {
    const app = createTestApp({
      services: {
        catalogBilling: {
          listModels: async () => [modelRecord, organizationModelRecord],
        },
      },
    });

    const response = await app.request("/api/v1/models");

    expect(response.status).toBe(200);
    const body = (await response.json()) as { data: { id: string }[] };
    expect(body.data.map((model) => model.id)).toEqual([modelRecord.id]);
  });
});
