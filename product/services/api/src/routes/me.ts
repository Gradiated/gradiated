import {
  CurrentUserSchema,
  problemContent,
  type CurrentUser,
} from "@gradiated/contracts";
import {
  companyEmailDomain,
  type OrganizationService,
  type UserOrganization,
} from "@gradiated/control";
import { createRoute, type OpenAPIHono } from "@hono/zod-openapi";

import { requireUser } from "../http/problems.js";
import { consoleOnly } from "../http/audience.js";
import type { ApiEnvironment } from "../types.js";

const getCurrentUserRoute = createRoute({
  ...consoleOnly,
  method: "get",
  path: "/api/v1/me",
  operationId: "getCurrentUser",
  summary: "Get current user",
  description: "Gets the signed-in user and the organizations they belong to.",
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
      company_email_domain: companyEmailDomain(user),
      image_url: user.image,
      created_at: user.createdAt.toISOString(),
      organizations: memberships.map(toCurrentOrganization),
    };

    return context.json(response, 200);
  });
};

export const toCurrentOrganization = (
  organization: UserOrganization,
): CurrentUser["organizations"][number] => ({
  id: organization.id,
  name: organization.name,
  status: organization.status,
  role: organization.role,
  default_workspace_id: organization.defaultWorkspaceId,
  auto_join_domain: organization.autoJoinDomain,
  onboarding_completed: organization.onboardingCompleted,
});
