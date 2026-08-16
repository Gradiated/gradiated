import {
  CurrentUserSchema,
  problemContent,
  type CurrentUser,
} from "@gradiated/contracts";
import { createRoute, type OpenAPIHono } from "@hono/zod-openapi";

import { problemDocument } from "../http/problem-response.js";
import type { ApiEnvironment, ApiServices } from "../types.js";

const getCurrentUserRoute = createRoute({
  method: "get",
  path: "/api/v1/me",
  operationId: "getCurrentUser",
  tags: ["Session"],
  responses: {
    200: {
      description: "The current user and their visible customer organizations.",
      content: { "application/json": { schema: CurrentUserSchema } },
    },
    401: {
      description: "No valid human session is present.",
      content: problemContent,
    },
  },
});

export function registerMeRoutes(
  app: OpenAPIHono<ApiEnvironment>,
  services: ApiServices,
): void {
  app.openapi(getCurrentUserRoute, async (context) => {
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

    const organizations = await services.organizations.listForUser(user.id);
    const response: CurrentUser = {
      id: user.id,
      name: user.name,
      email: user.email,
      email_verified: user.emailVerified,
      image_url: user.image,
      created_at: user.createdAt.toISOString(),
      organizations: organizations.map((organization) => ({
        id: organization.id,
        name: organization.name,
        status: organization.status,
        role: organization.role,
        default_workspace_id: organization.defaultWorkspaceId,
      })),
    };

    return context.json(response, 200);
  });
}
