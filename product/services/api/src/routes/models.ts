import {
  ModelListSchema,
  SERVICE_TIER_PRICING_POLICY,
  type Model,
} from "@gradiated/contracts";
import type { CatalogBillingService, ModelRecord } from "@gradiated/control";
import { createRoute, type OpenAPIHono } from "@hono/zod-openapi";

import type { ApiEnvironment } from "../types.js";

const MODEL_CATALOG_CACHE_CONTROL =
  "public, max-age=15, s-maxage=15, stale-while-revalidate=15";

const listModelsRoute = createRoute({
  method: "get",
  path: "/api/v1/models",
  operationId: "listModels",
  tags: ["Models"],
  responses: {
    200: {
      description: "The public catalog of supported exact models and prices.",
      headers: {
        "Cache-Control": {
          description:
            "Caches the public model catalog for 15 seconds and permits stale responses while the cache refreshes.",
          schema: { type: "string" },
        },
      },
      content: { "application/json": { schema: ModelListSchema } },
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
  created_at: record.createdAt.toISOString(),
  updated_at: record.updatedAt.toISOString(),
});

export const registerModelRoutes = (
  app: OpenAPIHono<ApiEnvironment>,
  catalog: Pick<CatalogBillingService, "listModels">,
): void => {
  app.openapi(listModelsRoute, async (context) => {
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
