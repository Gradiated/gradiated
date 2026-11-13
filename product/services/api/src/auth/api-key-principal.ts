import type { WorkspaceApiKeyService } from "@gradiated/control";

import type { SessionUser } from "../types.js";

// Keys cannot mint or revoke credentials, and cannot change or delete their workspace.
const DENIED_WORKSPACE_PATHS = /^\/(api-keys|playground-credentials)(\/|$)/;

export const bearerSecret = (headers: Headers): string | undefined => {
  const authorization = headers.get("authorization");
  const match = authorization?.match(/^Bearer\s+(grad_\S+)$/i);

  return match?.[1] ?? headers.get("x-api-key") ?? undefined;
};

export const isKeyAllowed = (workspaceId: string, path: string): boolean => {
  const prefix = `/api/v1/workspaces/${workspaceId}`;
  if (path === prefix || path === `${prefix}/`) return false;
  if (!path.startsWith(`${prefix}/`)) return false;

  return !DENIED_WORKSPACE_PATHS.test(path.slice(prefix.length));
};

// A workspace API key acts as the member who created it, only inside that workspace.
export const resolveApiKeyUser = async (
  apiKeys: Pick<WorkspaceApiKeyService, "authenticateApiKey">,
  request: { headers: Headers; path: string },
): Promise<SessionUser | null> => {
  const secret = bearerSecret(request.headers);
  if (!secret) return null;

  const owner = await apiKeys.authenticateApiKey(secret);
  if (!owner || !isKeyAllowed(owner.workspaceId, request.path)) return null;

  return { ...owner.user, impersonatedBy: null, impersonationExpiresAt: null };
};
