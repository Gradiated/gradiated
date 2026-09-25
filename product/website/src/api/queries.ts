import type { components } from "./schema";
import { api, requireData } from "./client";

export type CurrentUser = components["schemas"]["CurrentUser"];
export type Workspace = components["schemas"]["Workspace"];
export type ApiKey = components["schemas"]["ApiKey"];
export type CreatedApiKey = components["schemas"]["CreatedApiKey"];
export type Model = components["schemas"]["Model"];

export const listModels = (): Promise<components["schemas"]["ModelList"]> =>
  requireData<components["schemas"]["ModelList"]>(
    api.GET("/api/v1/models", { credentials: "omit" }),
  );

export const getCurrentUser = (): Promise<CurrentUser> =>
  requireData<CurrentUser>(api.GET("/api/v1/me"));

export const listWorkspaces = (
  organizationId: string,
): Promise<components["schemas"]["WorkspaceList"]> =>
  requireData<components["schemas"]["WorkspaceList"]>(
    api.GET("/api/v1/organizations/{organization_id}/workspaces", {
      params: { path: { organization_id: organizationId } },
    }),
  );

export const listApiKeys = (
  organizationId: string,
  workspaceId: string,
): Promise<components["schemas"]["ApiKeyList"]> =>
  requireData<components["schemas"]["ApiKeyList"]>(
    api.GET("/api/v1/workspaces/{workspace_id}/api-keys", {
      params: {
        path: {
          workspace_id: workspaceId,
        },
      },
    }),
  );

export const createApiKey = (
  organizationId: string,
  workspaceId: string,
): Promise<CreatedApiKey> =>
  requireData<CreatedApiKey>(
    api.POST("/api/v1/workspaces/{workspace_id}/api-keys", {
      params: {
        path: {
          workspace_id: workspaceId,
        },
      },
      body: { name: "Quickstart" },
    }),
  );
