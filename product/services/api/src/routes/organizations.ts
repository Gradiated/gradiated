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
import { createRoute, z, type OpenAPIHono } from "@hono/zod-openapi";

import { consoleOnly } from "../http/audience.js";
import { ApiProblem, problems, requireUser } from "../http/problems.js";
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
  organizations: Pick<
    OrganizationService,
    "createForUser" | "updateForUser" | "listForUser"
  >,
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

  app.openapi(
    createRoute({
      ...consoleOnly,
      method: "get",
      path: "/api/v1/admin/organizations",
      operationId: "listStaffOrganizations",
      summary: "Search customer organizations",
      description:
        "Returns a bounded page of customer organizations for verified staff, ordered by creation time and ID.",
      tags: ["Organizations"],
      request: {
        query: z.object({
          search: z
            .string()
            .trim()
            .max(200)
            .default("")
            .describe("Case-insensitive organization name substring."),
          limit: z.coerce
            .number()
            .int()
            .min(1)
            .max(100)
            .default(20)
            .describe("Maximum organizations per page."),
          offset: z.coerce
            .number()
            .int()
            .min(0)
            .max(10000000)
            .default(0)
            .describe("Number of matching organizations to skip."),
        }),
      },
      responses: {
        200: {
          description: "Matching organizations.",
          content: {
            "application/json": {
              schema: z.object({
                data: z.array(CurrentOrganizationSchema),
                has_more: z.boolean().describe("Whether another page exists."),
              }),
            },
          },
        },
        401: {
          description: "Authentication required.",
          content: problemContent,
        },
        403: { description: "Staff required.", content: problemContent },
        422: { description: "Invalid query.", content: problemContent },
      },
    }),
    async (context) => {
      const user = await requireUser(context);
      if (!user.isStaff || !user.emailVerified)
        throw new ApiProblem(problems.forbidden("Staff access required."));

      const query = context.req.valid("query");
      const rows = await organizations.listForUser(user.id, undefined, {
        ...query,
        limit: query.limit + 1,
      });

      return context.json(
        {
          data: rows.slice(0, query.limit).map(toCurrentOrganization),
          has_more: rows.length > query.limit,
        },
        200,
      );
    },
  );

  app.openapi(
    createRoute({
      ...consoleOnly,
      method: "get",
      path: "/api/v1/admin/organizations/{organization_id}",
      operationId: "getStaffOrganization",
      summary: "Get a customer organization",
      description:
        "Loads a single customer organization for verified staff without expanding the session bootstrap payload.",
      tags: ["Organizations"],
      request: { params: OrganizationIdParamsSchema },
      responses: {
        200: {
          description: "Customer organization.",
          content: {
            "application/json": { schema: CurrentOrganizationSchema },
          },
        },
        401: {
          description: "Authentication required.",
          content: problemContent,
        },
        403: { description: "Staff required.", content: problemContent },
        404: {
          description: "Organization not found.",
          content: problemContent,
        },
        422: {
          description: "Invalid organization ID.",
          content: problemContent,
        },
      },
    }),
    async (context) => {
      const user = await requireUser(context);
      if (!user.isStaff || !user.emailVerified || user.impersonatedBy)
        throw new ApiProblem(problems.forbidden("Staff access required."));

      const { organization_id } = context.req.valid("param");
      const [organization] = await organizations.listForUser(
        user.id,
        organization_id,
      );
      if (!organization)
        throw new ApiProblem(problems.notFound("Organization not found."));

      return context.json(toCurrentOrganization(organization), 200);
    },
  );

  const staffCreateRoute = createRoute({
    ...createOrganizationRoute,
    ...consoleOnly,
    path: "/api/v1/admin/organizations",
    operationId: "createStaffOrganization",
    summary: "Prepare a customer organization",
    description:
      "Staff create an organization and remain an admin to configure its workspace and invite customers.",
    responses: {
      ...createOrganizationRoute.responses,
      403: { description: "Staff access required.", content: problemContent },
    },
  });

  for (const route of [createOrganizationRoute, staffCreateRoute]) {
    app.openapi(route, async (context) => {
      const user = await requireUser(context);
      if (route === staffCreateRoute && (!user.isStaff || !user.emailVerified))
        throw new ApiProblem(problems.forbidden("Staff access required."));

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
  }
};
