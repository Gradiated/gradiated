import {
  infiniteQueryOptions,
  queryOptions,
  useMutation,
  useQueryClient,
} from "@tanstack/react-query";

import type { components, operations } from "./schema";
import { api, requireData, requireOk } from "./client";

export type CurrentUser = components["schemas"]["CurrentUser"];
export type Organization = components["schemas"]["Organization"];
export type Workspace = components["schemas"]["Workspace"];
export type ApiKey = components["schemas"]["ApiKey"];
export type CreatedApiKey = components["schemas"]["CreatedApiKey"];
export type Model = components["schemas"]["Model"];
export type ServiceTierPricingPolicy =
  components["schemas"]["ServiceTierPricingPolicy"];
export type BalanceTransaction = components["schemas"]["BalanceTransaction"];
export type UsageRange = operations["getUsageSummary"]["parameters"]["query"];
export type UsageSummary =
  operations["getUsageSummary"]["responses"][200]["content"]["application/json"];
export type GenerationLogQuery = Omit<
  NonNullable<operations["listGenerations"]["parameters"]["query"]>,
  "task_id"
> & { from: string; to: string };
export type GenerationLog = Extract<
  operations["listGenerations"]["responses"][200]["content"]["application/json"]["data"][number],
  { id: string }
>;

export const getCurrentUser = () => requireData(api.GET("/api/v1/me"));

export const createOrganization = (
  body: components["schemas"]["CreateOrganization"],
) => requireData(api.POST("/api/v1/organizations", { body }));

export const updateOrganization = (
  organizationId: string,
  body: components["schemas"]["UpdateOrganization"],
) =>
  requireData(
    api.PATCH("/api/v1/organizations/{organization_id}", {
      params: { path: { organization_id: organizationId } },
      body,
    }),
  );

export const listWorkspaces = (organizationId: string) =>
  requireData(
    api.GET("/api/v1/organizations/{organization_id}/workspaces", {
      params: { path: { organization_id: organizationId } },
    }),
  );

export type UpdateWorkspace = components["schemas"]["UpdateWorkspace"];
export const updateWorkspace = (
  organization: string,
  workspace: string,
  body: UpdateWorkspace,
) =>
  requireData(
    api.PATCH("/api/v1/workspaces/{workspace_id}", {
      params: {
        path: { workspace_id: workspace },
      },
      body,
    }),
  );

export const createWorkspace = (
  organizationId: string,
  body: components["schemas"]["CreateWorkspace"],
) =>
  requireData(
    api.POST("/api/v1/organizations/{organization_id}/workspaces", {
      params: { path: { organization_id: organizationId } },
      body,
    }),
  );

export const createTopUpCheckout = (organizationId: string, amount: string) =>
  requireData(
    api.POST("/api/v1/organizations/{organization_id}/billing/top-ups", {
      params: { path: { organization_id: organizationId } },
      body: { amount },
    }),
  );

const createApiKey = (
  organizationId: string,
  workspaceId: string,
  body: components["schemas"]["CreateApiKey"],
) =>
  requireData(
    api.POST("/api/v1/workspaces/{workspace_id}/api-keys", {
      params: {
        path: { workspace_id: workspaceId },
      },
      body,
    }),
  );

export const revokeApiKey = (
  organizationId: string,
  workspaceId: string,
  apiKeyId: string,
) =>
  requireOk(
    api.DELETE("/api/v1/workspaces/{workspace_id}/api-keys/{api_key_id}", {
      params: {
        path: {
          workspace_id: workspaceId,
          api_key_id: apiKeyId,
        },
      },
    }),
  );

export const modelsQuery = () =>
  queryOptions({
    queryKey: ["models"],
    queryFn: () => requireData(api.GET("/api/v1/models")),
  });

export const apiKeysQuery = (organizationId: string, workspaceId: string) =>
  queryOptions({
    queryKey: ["api-keys", organizationId, workspaceId],
    queryFn: () =>
      requireData(
        api.GET("/api/v1/workspaces/{workspace_id}/api-keys", {
          params: {
            path: {
              workspace_id: workspaceId,
            },
          },
        }),
      ),
    enabled: Boolean(organizationId && workspaceId),
  });

export const billingAccountQuery = (organizationId: string) =>
  queryOptions({
    queryKey: ["billing", organizationId],
    queryFn: () =>
      requireData(
        api.GET("/api/v1/organizations/{organization_id}/billing", {
          params: { path: { organization_id: organizationId } },
        }),
      ),
    enabled: Boolean(organizationId),
  });

export const balanceTransactionsQuery = (organizationId: string) =>
  infiniteQueryOptions({
    queryKey: ["balance-transactions", organizationId],
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam: cursor }) =>
      requireData(
        api.GET(
          "/api/v1/organizations/{organization_id}/balance-transactions",
          {
            params: {
              path: { organization_id: organizationId },
              query: { limit: 100, ...(cursor ? { cursor } : {}) },
            },
          },
        ),
      ),
    getNextPageParam: (page) => page.next_cursor ?? undefined,
    enabled: Boolean(organizationId),
  });

export const usageQuery = (
  organizationId: string,
  workspaceId: string,
  range: UsageRange,
) =>
  queryOptions({
    queryKey: ["usage", organizationId, workspaceId, range],
    queryFn: () =>
      requireData(
        api.GET("/api/v1/workspaces/{workspace_id}/usage", {
          params: {
            path: {
              workspace_id: workspaceId,
            },
            query: range,
          },
        }),
      ),
    enabled: Boolean(organizationId && workspaceId),
  });

export const generationLogsQuery = (
  organizationId: string,
  workspaceId: string,
  params: GenerationLogQuery,
) =>
  queryOptions({
    queryKey: ["generation-logs", organizationId, workspaceId, params],
    queryFn: () =>
      requireData(
        api.GET("/api/v1/workspaces/{workspace_id}/generations", {
          params: {
            path: {
              workspace_id: workspaceId,
            },
            query: params,
          },
        }),
      ).then((page) => ({
        ...page,
        data: page.data.map((row) => {
          if (!("id" in row))
            throw new Error("Expected hosted generation metadata.");
          return row;
        }),
      })),
    enabled: Boolean(organizationId && workspaceId),
  });

export const useCreateApiKey = (
  organizationId: string,
  workspaceId: string,
) => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (body: components["schemas"]["CreateApiKey"]) =>
      createApiKey(organizationId, workspaceId, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: apiKeysQuery(organizationId, workspaceId).queryKey,
      });
    },
  });
};

export const externalModelsQuery = () =>
  queryOptions({
    queryKey: ["models", "external"],
    queryFn: () =>
      requireData(
        api.GET("/api/v1/models", { params: { query: { external: "true" } } }),
      ),
    staleTime: 5 * 60 * 1000,
  });
