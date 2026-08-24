import type { components, operations } from "./schema";
import { api, requireData } from "./client";

export type CurrentUser = components["schemas"]["CurrentUser"];
export type Organization = components["schemas"]["Organization"];
export type Workspace = components["schemas"]["Workspace"];
export type ApiKey = components["schemas"]["ApiKey"];
export type CreatedApiKey = components["schemas"]["CreatedApiKey"];
export type Model = components["schemas"]["Model"];
export type BillingAccount = components["schemas"]["BillingAccount"];
export type BalanceTransaction = components["schemas"]["BalanceTransaction"];
export type UsageSummary =
  operations["getUsageSummary"]["responses"][200]["content"]["application/json"];
export type GenerationList =
  operations["listGenerations"]["responses"][200]["content"]["application/json"];
export type GenerationLog = GenerationList["data"][number];

export const getCurrentUser = () => {
  return requireData<CurrentUser>(api.GET("/api/v1/me"));
};

export const createOrganization = (body: { name: string }) => {
  return requireData<Organization>(api.POST("/api/v1/organizations", { body }));
};

export const listWorkspaces = (organizationId: string) => {
  return requireData<components["schemas"]["WorkspaceList"]>(
    api.GET("/api/v1/organizations/{organization_id}/workspaces", {
      params: { path: { organization_id: organizationId } },
    }),
  );
};

export const createWorkspace = (
  organizationId: string,
  body: { name: string },
) => {
  return requireData<Workspace>(
    api.POST("/api/v1/organizations/{organization_id}/workspaces", {
      params: { path: { organization_id: organizationId } },
      body,
    }),
  );
};

export const listModels = () => {
  return requireData<components["schemas"]["ModelList"]>(
    api.GET("/api/v1/models"),
  );
};

export const getUsageSummary = (
  organizationId: string,
  workspaceId: string,
  range: { from: string; to: string },
) => {
  return requireData<UsageSummary>(
    api.GET(
      "/api/v1/organizations/{organization_id}/workspaces/{workspace_id}/usage",
      {
        params: {
          path: {
            organization_id: organizationId,
            workspace_id: workspaceId,
          },
          query: range,
        },
      },
    ),
  );
};

export const listGenerationLogs = (
  organizationId: string,
  workspaceId: string,
  filters: {
    from: string;
    to: string;
    cursor?: string;
    limit?: number;
    api_key_id?: string;
    model?: string;
    search?: string;
    sort?: "newest" | "highest_cost";
    status?: GenerationLog["status"];
  },
) => {
  return requireData<GenerationList>(
    api.GET(
      "/api/v1/organizations/{organization_id}/workspaces/{workspace_id}/generations",
      {
        params: {
          path: {
            organization_id: organizationId,
            workspace_id: workspaceId,
          },
          query: filters,
        },
      },
    ),
  );
};

export const getBillingAccount = (organizationId: string) => {
  return requireData<BillingAccount>(
    api.GET("/api/v1/organizations/{organization_id}/billing", {
      params: { path: { organization_id: organizationId } },
    }),
  );
};

export const listBalanceTransactions = (organizationId: string) => {
  return requireData<components["schemas"]["BalanceTransactionList"]>(
    api.GET("/api/v1/organizations/{organization_id}/balance-transactions", {
      params: { path: { organization_id: organizationId } },
    }),
  );
};

export const createTopUpCheckout = (organizationId: string, amount: string) => {
  return requireData<components["schemas"]["TopUpCheckout"]>(
    api.POST("/api/v1/organizations/{organization_id}/billing/top-ups", {
      params: { path: { organization_id: organizationId } },
      body: { amount },
    }),
  );
};

export const listApiKeys = (organizationId: string, workspaceId: string) => {
  return requireData<components["schemas"]["ApiKeyList"]>(
    api.GET(
      "/api/v1/organizations/{organization_id}/workspaces/{workspace_id}/api-keys",
      {
        params: {
          path: {
            organization_id: organizationId,
            workspace_id: workspaceId,
          },
        },
      },
    ),
  );
};

export const createApiKey = (
  organizationId: string,
  workspaceId: string,
  body: { name: string; expires_at?: string | null },
) => {
  return requireData<CreatedApiKey>(
    api.POST(
      "/api/v1/organizations/{organization_id}/workspaces/{workspace_id}/api-keys",
      {
        params: {
          path: {
            organization_id: organizationId,
            workspace_id: workspaceId,
          },
        },
        body,
      },
    ),
  );
};

export const revokeApiKey = async (
  organizationId: string,
  workspaceId: string,
  apiKeyId: string,
) => {
  const { response, error } = await api.DELETE(
    "/api/v1/organizations/{organization_id}/workspaces/{workspace_id}/api-keys/{api_key_id}",
    {
      params: {
        path: {
          organization_id: organizationId,
          workspace_id: workspaceId,
          api_key_id: apiKeyId,
        },
      },
    },
  );
  if (!response.ok) {
    const detail =
      error && typeof error === "object" && "detail" in error
        ? String(error.detail)
        : "The API key could not be revoked.";
    throw new Error(detail);
  }
};
