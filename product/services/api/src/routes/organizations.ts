import { changedFields } from "@gradiated/analytics";
import {
  CreateOrganizationSchema,
  CurrentOrganizationSchema,
  UpdateOrganizationSchema,
  OrganizationIdParamsSchema,
  OrganizationSchema,
  problemContent,
  type Organization,
} from "@gradiated/contracts";
import type { OrganizationService } from "@gradiated/control";
import { createRoute, type OpenAPIHono } from "@hono/zod-openapi";

import { requireUser } from "../http/problems.js";
import { toCurrentOrganization } from "./me.js";
import type { ApiEnvironment } from "../types.js";

const createOrganizationRoute = createRoute({
  method: "post",
  path: "/api/v1/organizations",
  operationId: "createOrganization",
  summary: "Create organization",
  description: "Creates an organization.",
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

const updateOrganizationRoute = createRoute({
  method: "patch",
  path: "/api/v1/organizations/{organization_id}",
  operationId: "updateOrganization",
  summary: "Update organization",
  description: "Changes the organization's settings.",
  tags: ["Organizations"],
  request: {
    params: OrganizationIdParamsSchema,
    body: {
      required: true,
      content: { "application/json": { schema: UpdateOrganizationSchema } },
    },
  },
  responses: {
    200: {
      description: "Updated organization settings.",
      content: { "application/json": { schema: CurrentOrganizationSchema } },
    },
    401: { description: "Authentication required.", content: problemContent },
    403: {
      description: "Organization management denied.",
      content: problemContent,
    },
    404: { description: "Organization not found.", content: problemContent },
    409: {
      description:
        "Another organization already lets this email domain join automatically.",
      content: problemContent,
    },
    422: {
      description: "Invalid organization update.",
      content: problemContent,
    },
  },
});

export const registerOrganizationRoutes = (
  app: OpenAPIHono<ApiEnvironment>,
  organizations: Pick<OrganizationService, "createForUser" | "updateForUser">,
): void => {
  app.openapi(updateOrganizationRoute, async (context) => {
    const user = await requireUser(context);
    const { organization_id } = context.req.valid("param");
    const updated = await organizations.updateForUser(
      user.id,
      organization_id,
      context.req.valid("json"),
    );

    context.get("analytics")?.track(user.id, "organization_settings_updated", {
      organization_id,
      changed_fields: changedFields(context.req.valid("json")),
    });

    return context.json(
      CurrentOrganizationSchema.parse(toCurrentOrganization(updated)),
      200,
    );
  });

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

    context.get("analytics")?.track(user.id, "organization_created", {
      organization_id: created.id,
      default_workspace_id: created.defaultWorkspaceId,
    });
    context.get("analytics")?.track(user.id, "workspace_created", {
      organization_id: created.id,
      workspace_id: created.defaultWorkspaceId,
      is_default: true,
    });

    return context.json(response, 201);
  });
};
