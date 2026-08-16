import {
  CreateOrganizationSchema,
  OrganizationSchema,
  problemContent,
  type Organization,
} from "@gradiated/contracts";
import { ControlServiceError } from "@gradiated/control";
import { createRoute, type OpenAPIHono } from "@hono/zod-openapi";

import { problemDocument } from "../http/problem-response.js";
import type { ApiEnvironment, ApiServices } from "../types.js";

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

export function registerOrganizationRoutes(
  app: OpenAPIHono<ApiEnvironment>,
  services: ApiServices,
): void {
  app.openapi(createOrganizationRoute, async (context) => {
    const user = context.get("user");
    if (!user) {
      return context.json(
        problemDocument(context, {
          type: "https://gradiated.com/problems/unauthenticated",
          title: "Authentication required",
          status: 401,
          detail: "A valid human session is required for this operation.",
          code: "unauthenticated",
        }),
        401,
        { "Content-Type": "application/problem+json" },
      );
    }

    const input = context.req.valid("json");
    let created;
    try {
      created = await services.organizations.createForUser(user.id, input.name);
    } catch (error) {
      if (
        !(error instanceof ControlServiceError) ||
        error.code !== "unavailable"
      ) {
        throw error;
      }
      return context.json(
        problemDocument(context, {
          type: "https://gradiated.com/problems/unavailable",
          title: "Serving state unavailable",
          status: 503,
          detail: error.message,
          code: error.code,
        }),
        503,
        { "Content-Type": "application/problem+json" },
      );
    }
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
}
