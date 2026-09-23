import { WizardKeyResponseSchema, problemContent } from "@gradiated/contracts";
import type {
  CatalogBillingService,
  OrganizationService,
  WorkspaceApiKeyService,
} from "@gradiated/control";
import { createRoute, type OpenAPIHono } from "@hono/zod-openapi";

import { ApiProblem, problems, requireUser } from "../http/problems.js";
import type { ApiEnvironment } from "../types.js";
import { apiKeyResponse } from "./api-key-response.js";

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
    403: {
      description: "The session user may not read the organization's billing.",
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

export const registerWizardRoutes = (
  app: OpenAPIHono<ApiEnvironment>,
  {
    organizations,
    billingAccounts,
    apiKeys,
  }: {
    organizations: Pick<OrganizationService, "listForUser">;
    billingAccounts: Pick<CatalogBillingService, "getBillingAccount">;
    apiKeys: Pick<WorkspaceApiKeyService, "createApiKey">;
  },
): void => {
  app.openapi(createWizardKeyRoute, async (context) => {
    const user = await requireUser(context);
    const [organization] = await organizations.listForUser(user.id);
    if (!organization) {
      throw new ApiProblem(
        problems.notFound(
          "The session user has no organization to mint a key on.",
          "No organization",
        ),
      );
    }

    const account = await billingAccounts.getBillingAccount(
      user.id,
      organization.id,
    );
    const created = await apiKeys.createApiKey(
      user.id,
      organization.id,
      organization.defaultWorkspaceId,
      { name: "local", expiresAt: null },
    );

    context.header("Cache-Control", "no-store");
    return context.json(
      {
        api_key: apiKeyResponse(created.apiKey),
        secret: created.secret,
        organization_id: organization.id,
        workspace_id: organization.defaultWorkspaceId,
        organization_name: organization.name,
        balance_nano_usd: Number(account.balance),
      },
      201,
    );
  });
};
