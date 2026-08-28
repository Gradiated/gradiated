import { WizardKeyResponseSchema, problemContent } from "@gradiated/contracts";
import { ControlServiceError } from "@gradiated/control";
import { createRoute, type OpenAPIHono } from "@hono/zod-openapi";

import { problemDocument } from "../http/problem-response.js";
import type { ApiEnvironment, ApiServices } from "../types.js";

const createWizardKeyRoute = createRoute({
  hide: true,
  method: "post",
  path: "/api/v1/wizard/key",
  operationId: "createWizardKey",
  tags: ["API keys"],
  responses: {
    201: {
      description:
        "A local API key minted on the session's organization, with its one-time secret.",
      headers: {
        "Cache-Control": {
          description: "Prevents storage of the one-time secret.",
          schema: { type: "string" },
        },
      },
      content: { "application/json": { schema: WizardKeyResponseSchema } },
    },
    401: {
      description: "No valid human session is present.",
      content: problemContent,
    },
    404: {
      description: "The session user has no organization.",
      content: problemContent,
    },
    503: {
      description: "Serving state is unavailable.",
      content: problemContent,
    },
  },
});

function controlError(
  context: Parameters<typeof problemDocument>[0],
  error: unknown,
) {
  if (!(error instanceof ControlServiceError)) throw error;
  if (error.code === "not_found") {
    return context.json(
      problemDocument(context, {
        type: "https://gradiated.com/problems/not-found",
        title: "Not found",
        status: 404,
        detail: error.message,
        code: error.code,
      }),
      404,
      { "Content-Type": "application/problem+json" },
    );
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

export function registerWizardRoutes(
  app: OpenAPIHono<ApiEnvironment>,
  services: ApiServices,
): void {
  app.openapi(createWizardKeyRoute, async (context) => {
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
    const organization = organizations[0];
    if (!organization) {
      return context.json(
        problemDocument(context, {
          type: "https://gradiated.com/problems/not-found",
          title: "No organization",
          status: 404,
          detail: "The session user has no organization to mint a key on.",
          code: "not_found",
        }),
        404,
        { "Content-Type": "application/problem+json" },
      );
    }

    try {
      const account = await services.catalogBilling.getBillingAccount(
        user.id,
        organization.id,
      );
      const created = await services.workspaces.createApiKey(
        user.id,
        organization.id,
        organization.defaultWorkspaceId,
        { name: "local", expiresAt: null },
      );
      context.header("Cache-Control", "no-store");
      return context.json(
        {
          api_key: {
            id: created.apiKey.id,
            organization_id: created.apiKey.organizationId,
            workspace_id: created.apiKey.workspaceId,
            name: created.apiKey.name,
            expires_at: created.apiKey.expiresAt?.toISOString() ?? null,
            revoked_at: created.apiKey.revokedAt?.toISOString() ?? null,
            created_by: created.apiKey.createdBy,
            created_at: created.apiKey.createdAt.toISOString(),
            updated_at: created.apiKey.updatedAt.toISOString(),
          },
          secret: created.secret,
          organization_id: organization.id,
          workspace_id: organization.defaultWorkspaceId,
          organization_name: organization.name,
          balance_nano_usd: Number(account.balance),
        },
        201,
      );
    } catch (error) {
      return controlError(context, error);
    }
  });
}
