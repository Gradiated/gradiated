import {
  CreateOrganizationSchema,
  OrganizationSchema,
  problemContent,
  type Organization,
} from "@gradiated/contracts";
import type { OrganizationService } from "@gradiated/control";
import { createRoute, type OpenAPIHono } from "@hono/zod-openapi";

import { requireUser } from "../http/problems.js";
import type { ApiEnvironment } from "../types.js";

const createOrganizationRoute = createRoute({
  method: "post",
  path: "/api/v1/organizations",
  operationId: "createOrganization",
  tags: ["Organizations"],
  request: {
    body: {
      required: true,
      content: { "application/json": { schema: CreateOrganizationSchema } },
    },
  },
  responses: {
    201: {
      description:
        "The organization and its launch defaults were created atomically.",
      content: { "application/json": { schema: OrganizationSchema } },
    },
    401: {
      description: "No valid human session is present.",
      content: problemContent,
    },
    422: {
      description: "The request body is invalid.",
      content: problemContent,
    },
    503: {
      description: "Serving state is unavailable.",
      content: problemContent,
    },
  },
});

export const registerOrganizationRoutes = (
  app: OpenAPIHono<ApiEnvironment>,
  organizations: Pick<OrganizationService, "createForUser">,
): void => {
  app.openapi(createOrganizationRoute, async (context) => {
    const user = await requireUser(context);
    const input = context.req.valid("json");
    const created = await organizations.createForUser(user.id, input.name);
    const response: Organization = {
      id: created.id,
      kind: created.kind,
      name: created.name,
      status: created.status,
      role: created.role,
      default_workspace_id: created.defaultWorkspaceId,
      created_at: created.createdAt.toISOString(),
      updated_at: created.updatedAt.toISOString(),
    };

    return context.json(response, 201);
  });
};
