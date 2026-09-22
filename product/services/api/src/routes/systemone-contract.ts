import {
  SystemOneRequestSchema,
  SystemOneResponseSchema,
} from "@gradiated/contracts";
import type { OpenAPIHono } from "@hono/zod-openapi";

import type { ApiEnvironment } from "../types.js";

/** Documentation only. The Rust gateway serves and authenticates this route. */
export const registerSystemOneContract = (app: OpenAPIHono<ApiEnvironment>) => {
  app.openAPIRegistry.registerComponent("securitySchemes", "InferenceBearer", {
    type: "http",
    scheme: "bearer",
    description: "Workspace API key for the Rust inference gateway.",
  });
  app.openAPIRegistry.registerPath({
    method: "post",
    path: "/v1/systemone",
    operationId: "systemOne",
    tags: ["Inference"],
    summary: "Answer named questions with native SystemOne inference",
    description:
      "Served by the Rust gateway. Requires an exact hosted model and a workspace API key. Supports choice, noul and score questions over text or structured state. No streaming or generated output tokens; only the default service tier is implemented.",
    security: [{ InferenceBearer: [] }],
    request: {
      body: {
        required: true,
        content: { "application/json": { schema: SystemOneRequestSchema } },
      },
    },
    responses: {
      200: {
        description:
          "Native answers and authoritative input/cache usage; output_tokens is always zero.",
        content: { "application/json": { schema: SystemOneResponseSchema } },
      },
      400: {
        description: "Invalid request or unsupported inference parameter.",
      },
      401: { description: "Missing or invalid workspace API key." },
      402: { description: "The prepaid account has insufficient balance." },
      404: {
        description: "The exact requested model is unavailable or unknown.",
      },
      413: { description: "The request exceeds the gateway body limit." },
      429: { description: "Admission or inference capacity is exhausted." },
      503: {
        description:
          "Runtime failure, invalid native response, no healthy deployment, or an unavailable gateway dependency.",
      },
    },
  });
};
