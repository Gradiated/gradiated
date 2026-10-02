import {
  ModelListSchema,
  ProblemSchema,
  SERVICE_TIER_PRICING_POLICY,
  type Model,
} from "@gradiated/contracts";
import type { CatalogBillingService, ModelRecord } from "@gradiated/control";
import { createRoute, z, type OpenAPIHono } from "@hono/zod-openapi";
import { catalogModel } from "@gradiated/contracts/model-catalog";
import type { createExternalModelCatalog } from "../catalog/external-models.js";

import type { ApiEnvironment } from "../types.js";

const MODEL_CATALOG_CACHE_CONTROL =
  "public, max-age=15, s-maxage=15, stale-while-revalidate=15";

const listModelsRoute = createRoute({
  method: "get",
  path: "/api/v1/models",
  operationId: "listModels",
  tags: ["Models"],
  request: {
    query: z.object({
      external: z
        .enum(["true", "false"])
        .optional()
        .describe(
          "Return the supported external provider catalog instead of hosted models. External prices are estimates and cached in API memory for five minutes.",
        ),
    }),
  },
  responses: {
    200: {
      description: "The public catalog of supported exact models and prices.",
      headers: {
        "Cache-Control": {
          description:
            "Caches hosted models for 15 seconds with stale-while-revalidate, or external models for 60 seconds.",
          schema: { type: "string" },
        },
      },
      content: { "application/json": { schema: ModelListSchema } },
    },
    503: {
      description: "The requested model catalog is unavailable.",
      content: { "application/problem+json": { schema: ProblemSchema } },
    },
  },
});

type ListedModelRecord = ModelRecord & {
  status: Exclude<ModelRecord["status"], "retired">;
};

const isListedModel = (record: ModelRecord): record is ListedModelRecord =>
  record.status !== "retired";

const modelResponse = (record: ListedModelRecord): Model => ({
  id: record.id,
  name: record.name,
  status: record.status,
  properties: record.properties,
  icon: catalogModel(record.id)?.icon ?? null,
  created_at: record.createdAt.toISOString(),
  updated_at: record.updatedAt.toISOString(),
});

export const registerModelRoutes = (
  app: OpenAPIHono<ApiEnvironment>,
  catalog: Pick<CatalogBillingService, "listModels">,
  externalModels: ReturnType<typeof createExternalModelCatalog>,
): void => {
  app.openapi(listModelsRoute, async (context) => {
    if (context.req.valid("query").external === "true") {
      const models = await externalModels();
      context.header("Cache-Control", "public, max-age=60");

      return context.json(models, 200);
    }

    const records = await catalog.listModels();

    context.header("Cache-Control", MODEL_CATALOG_CACHE_CONTROL);

    return context.json(
      {
        data: records.filter(isListedModel).map(modelResponse),
        next_cursor: null,
        service_tiers: [...SERVICE_TIER_PRICING_POLICY],
      },
      200,
    );
  });
};
