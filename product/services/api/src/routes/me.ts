import {
  CurrentUserSchema,
  problemContent,
  type CurrentUser,
} from "@gradiated/contracts";
import type { OrganizationService } from "@gradiated/control";
import { createRoute, type OpenAPIHono } from "@hono/zod-openapi";

import { requireUser } from "../http/problems.js";
import type { ApiEnvironment } from "../types.js";

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

export const registerMeRoutes = (
  app: OpenAPIHono<ApiEnvironment>,
  organizations: Pick<OrganizationService, "listForUser">,
): void => {
  app.openapi(getCurrentUserRoute, async (context) => {
    const user = await requireUser(context);
    const memberships = await organizations.listForUser(user.id);
    const response: CurrentUser = {
      id: user.id,
      name: user.name,
      email: user.email,
      email_verified: user.emailVerified,
      image_url: user.image,
      created_at: user.createdAt.toISOString(),
      organizations: memberships.map((organization) => ({
        id: organization.id,
        name: organization.name,
        status: organization.status,
        role: organization.role,
        default_workspace_id: organization.defaultWorkspaceId,
      })),
    };

    return context.json(response, 200);
  });
};
