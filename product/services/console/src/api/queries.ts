import {
  infiniteQueryOptions,
  queryOptions,
  useMutation,
  useQueryClient,
} from "@tanstack/react-query";

import { toast } from "sonner";

import type { components, operations } from "./schema";
import { switchConsoleIdentity } from "@/lib/session-sync";
import {
  api,
  ApiError,
  needsStaffSessionRecovery,
  requireData,
  requireOk,
} from "./client";

export type CurrentUser = components["schemas"]["CurrentUser"];
export type Organization = components["schemas"]["Organization"];
export type Workspace = components["schemas"]["Workspace"];
export type ApiKey = components["schemas"]["ApiKey"];
export type CreatedApiKey = components["schemas"]["CreatedApiKey"];
export type OrganizationRole = components["schemas"]["OrganizationRole"];
export type Member = components["schemas"]["Member"];
export type Invitation = components["schemas"]["Invitation"];
export type InvitationPreview = components["schemas"]["InvitationPreview"];
type ModelList =
  | components["schemas"]["ModelList"]
  | components["schemas"]["ExternalModelList"];

export type Model =
  components["schemas"]["Model"] | components["schemas"]["ExternalModel"];
export type ServiceTierPricingPolicy =
  components["schemas"]["ServiceTierPricingPolicy"];
export type BalanceTransaction = components["schemas"]["BalanceTransaction"];
export type BillingAccount = components["schemas"]["BillingAccount"];
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

let staffRecovery: Promise<CurrentUser> | undefined;

export const getCurrentUser = async (): Promise<CurrentUser> => {
  try {
    return await requireData(api.GET("/api/v1/me"));
  } catch (error) {
    if (!needsStaffSessionRecovery(error)) throw error;

    staffRecovery ??= (async () => {
      try {
        await stopImpersonation();
      } catch (restoreError) {
        if (!(restoreError instanceof ApiError) || restoreError.status !== 401)
          throw restoreError;
        // Another tab may already have restored the shared cookie.
      }
      const user = await requireData(api.GET("/api/v1/me"));
      switchConsoleIdentity("/admin");
      return user;
    })().finally(() => {
      staffRecovery = undefined;
    });

    return staffRecovery;
  }
};

export const startImpersonation = (userId: string) =>
  requireData(
    api.POST("/api/v1/admin/impersonations", { body: { user_id: userId } }),
  );
export const stopImpersonation = () =>
  requireData(api.POST("/api/v1/admin/impersonations/stop"));

export const createOrganization = (
  body: components["schemas"]["CreateOrganization"],
) => requireData(api.POST("/api/v1/organizations", { body }));

export const getStaffOrganization = (organizationId: string) =>
  requireData(
    api.GET("/api/v1/admin/organizations/{organization_id}", {
      params: { path: { organization_id: organizationId } },
    }),
  );

export const createStaffOrganization = (
  body: components["schemas"]["CreateOrganization"],
) => requireData(api.POST("/api/v1/admin/organizations", { body }));

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

const organizationPath = (organizationId: string) => ({
  params: { path: { organization_id: organizationId } },
});

export const listMembers = (organizationId: string) =>
  requireData(
    api.GET(
      "/api/v1/organizations/{organization_id}/members",
      organizationPath(organizationId),
    ),
  );

export const updateMember = (
  organizationId: string,
  userId: string,
  role: OrganizationRole,
) =>
  requireData(
    api.PATCH("/api/v1/organizations/{organization_id}/members/{user_id}", {
      params: { path: { organization_id: organizationId, user_id: userId } },
      body: { role },
    }),
  );

export const removeMember = (organizationId: string, userId: string) =>
  requireOk(
    api.DELETE("/api/v1/organizations/{organization_id}/members/{user_id}", {
      params: { path: { organization_id: organizationId, user_id: userId } },
    }),
  );

export const listInvitations = (organizationId: string) =>
  requireData(
    api.GET(
      "/api/v1/organizations/{organization_id}/invitations",
      organizationPath(organizationId),
    ),
  );

export const createInvitations = (
  organizationId: string,
  body: components["schemas"]["CreateInvitations"],
) =>
  requireData(
    api.POST("/api/v1/organizations/{organization_id}/invitations", {
      ...organizationPath(organizationId),
      body,
    }),
  );

export const resendInvitation = (
  organizationId: string,
  invitationId: string,
) =>
  requireData(
    api.POST(
      "/api/v1/organizations/{organization_id}/invitations/{invitation_id}/resend",
      {
        params: {
          path: {
            organization_id: organizationId,
            invitation_id: invitationId,
          },
        },
      },
    ),
  );

export const revokeInvitation = (
  organizationId: string,
  invitationId: string,
) =>
  requireOk(
    api.DELETE(
      "/api/v1/organizations/{organization_id}/invitations/{invitation_id}",
      {
        params: {
          path: {
            organization_id: organizationId,
            invitation_id: invitationId,
          },
        },
      },
    ),
  );

export const previewInvitation = (token: string): Promise<InvitationPreview> =>
  requireData(api.POST("/api/v1/invitations/preview", { body: { token } }));

export const acceptInvitation = (token: string) =>
  requireData(api.POST("/api/v1/invitations/accept", { body: { token } }));

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

export const createTopUp = (
  organizationId: string,
  body: components["schemas"]["CreateTopUp"],
) =>
  requireData(
    api.POST("/api/v1/organizations/{organization_id}/billing/top-ups", {
      params: { path: { organization_id: organizationId } },
      body,
    }),
  );

export const updateAutoTopUp = (
  organizationId: string,
  autoTopUp: components["schemas"]["UpdateAutoTopUp"],
) =>
  requireData(
    api.PATCH("/api/v1/organizations/{organization_id}/billing", {
      params: { path: { organization_id: organizationId } },
      body: { auto_top_up: autoTopUp },
    }),
  );

export const createPaymentMethodSession = (organizationId: string) =>
  requireData(
    api.POST(
      "/api/v1/organizations/{organization_id}/billing/payment-method-sessions",
      { params: { path: { organization_id: organizationId } } },
    ),
  );

export const createCardSetup = (organizationId: string) =>
  requireData(
    api.POST("/api/v1/organizations/{organization_id}/billing/card-setups", {
      params: { path: { organization_id: organizationId } },
    }),
  );

export const saveCard = (organizationId: string, setupIntentId: string) =>
  requireData(
    api.POST("/api/v1/organizations/{organization_id}/billing/card", {
      params: { path: { organization_id: organizationId } },
      body: { setup_intent_id: setupIntentId },
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

const PLAYGROUND_CREDENTIAL_LIFETIME_MS = 60 * 60 * 1000;
const PLAYGROUND_CREDENTIAL_RENEWAL_MS = 5 * 60 * 1000;

export const playgroundCredentialQuery = (
  organizationId: string,
  workspaceId: string,
) =>
  queryOptions({
    queryKey: ["playground-credential", organizationId, workspaceId],
    queryFn: () =>
      requireData(
        api.POST("/api/v1/workspaces/{workspace_id}/playground-credentials", {
          params: { path: { workspace_id: workspaceId } },
        }),
      ),
    staleTime: ({ state }) =>
      state.data
        ? Math.max(
            Date.parse(state.data.expires_at) -
              Date.now() -
              PLAYGROUND_CREDENTIAL_RENEWAL_MS,
            0,
          )
        : 0,
    gcTime: PLAYGROUND_CREDENTIAL_LIFETIME_MS,
    enabled: Boolean(organizationId && workspaceId),
  });

export const modelsQuery = () =>
  queryOptions({
    queryKey: ["models"],
    queryFn: (): Promise<ModelList> => requireData(api.GET("/api/v1/models")),
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

// Saves a card Stripe confirmed, from the card dialog or a confirmation redirect.
export const useSaveCard = (organizationId: string) => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (setupIntentId: string) =>
      saveCard(organizationId, setupIntentId),
    meta: { errorMessage: "The card was not saved." },
    onSuccess: (account) => {
      queryClient.setQueryData(
        billingAccountQuery(organizationId).queryKey,
        account,
      );
      toast.success("Card saved", { id: "card-saved" });
    },
  });
};

export const externalModelsQuery = () =>
  queryOptions({
    queryKey: ["models", "external"],
    queryFn: (): Promise<ModelList> =>
      requireData(
        api.GET("/api/v1/models", { params: { query: { external: "true" } } }),
      ),
    staleTime: 5 * 60 * 1000,
  });

export const listStaffOrganizations = (search: string, offset: number) =>
  requireData(
    api.GET("/api/v1/admin/organizations", {
      params: { query: { search, offset, limit: 20 } },
    }),
  );
