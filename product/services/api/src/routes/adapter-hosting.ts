import { createRoute, type OpenAPIHono, z } from "@hono/zod-openapi";
import {
  AdapterDownloadSchema,
  TaskVersionSchema,
  UuidSchema,
  problemContent,
} from "@gradiated/contracts";
import {
  CertificateAuthorizationError,
  type InstanceCertificateService,
  type AdapterHostingService,
} from "@gradiated/control";
import { bearerToken } from "../ingest/http.js";
import type { ApiEnvironment } from "../types.js";
import { versionResponse } from "./training.js";

const target = z.strictObject({
  workspace_id: UuidSchema,
  version_name: TaskVersionSchema.shape.name.min(1).max(300),
});
const errors = {
  401: { description: "Missing or invalid enrolled host credential." },
  404: { description: "Version not found.", content: problemContent },
  422: { description: "Invalid request.", content: problemContent },
  503: { description: "Adapter unavailable.", content: problemContent },
};
const grant = createRoute({
  hide: true,
  method: "post",
  path: "/api/internal/v1/adapter-downloads",
  operationId: "createPrivateAdapterDownload",
  description:
    "Issue a versioned download grant for an exact workspace and immutable version slug. Candidates may be unavailable for serving; this route does not promote them.",
  request: {
    body: {
      required: true,
      content: { "application/json": { schema: target } },
    },
  },
  responses: {
    200: {
      description: "Immutable task version and temporary download grant.",
      content: {
        "application/json": {
          schema: z.object({
            workspace_id: UuidSchema,
            version: TaskVersionSchema,
            download: AdapterDownloadSchema,
          }),
        },
      },
    },
    ...errors,
  },
});
const production = createRoute({
  hide: true,
  method: "get",
  path: "/api/internal/v1/task-versions/production",
  operationId: "listPrivateProductionAdapters",
  description:
    "List at most 4096 current, available production versions for a base model, most recently updated task first. Hosts preload independently and verify local compatibility.",
  request: {
    query: z.object({ base_model_id: TaskVersionSchema.shape.base_model_id }),
  },
  responses: {
    200: {
      description:
        "Current production adapter identities; empty when none exist.",
      content: {
        "application/json": { schema: z.object({ data: z.array(target) }) },
      },
    },
    ...errors,
  },
});

export interface AdapterHostingDependencies {
  credentials: () => Promise<Pick<InstanceCertificateService, "authorize">>;
  service: AdapterHostingService;
}

export const registerAdapterHostingRoutes = (
  app: OpenAPIHono<ApiEnvironment>,
  {
    credentials,
    service,
  }: Pick<AdapterHostingDependencies, "service"> &
    Partial<Pick<AdapterHostingDependencies, "credentials">>,
  privateListener = false,
) => {
  if (!privateListener && !credentials)
    throw new Error("Public adapter routes require host authentication");

  for (const route of [grant, production]) {
    app.use(route.getRoutingPath(), async (context, next) => {
      context.header("Cache-Control", "no-store");
      if (privateListener) return next();

      const supplied = bearerToken(context.req.header("authorization"));
      const instance = UuidSchema.safeParse(
        context.req.header("X-Gradiated-Instance-Id"),
      );
      const node = UuidSchema.safeParse(
        context.req.header("X-Gradiated-Nomad-Node-Id"),
      );
      if (
        !supplied ||
        !/^[A-Za-z0-9_-]{43}$/.test(supplied) ||
        !instance.success ||
        !node.success
      )
        return context.body(null, 401);

      try {
        await (
          await credentials!()
        ).authorize(instance.data, node.data, supplied);
      } catch (error) {
        if (error instanceof CertificateAuthorizationError)
          return context.body(null, 401);

        throw error;
      }

      await next();
    });
  }

  app.openapi(grant, async (context) => {
    const body = context.req.valid("json");
    const row = await service.grant(body.workspace_id, body.version_name);

    return context.json(
      {
        workspace_id: row.version.workspaceId,
        version: versionResponse(row.task, row.version),
        download: AdapterDownloadSchema.parse(row.download),
      },
      200,
    );
  });
  app.openapi(production, async (context) => {
    const query = context.req.valid("query");
    const data = await service.productionVersions(query.base_model_id);

    return context.json({ data }, 200);
  });
};
