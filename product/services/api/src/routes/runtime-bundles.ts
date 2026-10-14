import { createRoute, type OpenAPIHono, z } from "@hono/zod-openapi";
import { problemContent } from "@gradiated/contracts";
import { problemResponse, problems } from "../http/problems.js";
import type { ApiEnvironment } from "../types.js";

const route = createRoute({
  hide: true,
  method: "get",
  path: "/api/internal/v1/runtime-bundles/{sha256}",
  operationId: "getPrivateRuntimeBundle",
  description:
    "Issue a temporary download URL for one published runtime bundle.",
  request: {
    params: z.object({
      sha256: z
        .string()
        .regex(/^[0-9a-f]{64}$/)
        .describe("The immutable bundle digest"),
    }),
  },
  responses: {
    200: {
      description: "A temporary bundle download grant.",
      content: {
        "application/json": {
          schema: z.object({
            url: z.url().describe("The temporary download URL"),
          }),
        },
      },
    },
    404: { description: "Bundle not found.", content: problemContent },
  },
});

export const registerRuntimeBundleRoutes = (
  app: OpenAPIHono<ApiEnvironment>,
  download: (digest: string) => Promise<{ url: string } | undefined>,
) => {
  app.openapi(route, async (context) => {
    context.header("Cache-Control", "no-store");
    const grant = await download(context.req.valid("param").sha256);
    if (!grant)
      return problemResponse(context, {
        ...problems.notFound("Runtime bundle not found."),
        status: 404,
      });
    return context.json(grant, 200);
  });
};
