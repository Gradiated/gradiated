import {
  OAUTH_ACCESS_TOKEN_PREFIX,
  type WorkspaceApiKeyService,
} from "@gradiated/control";

import type { SessionUser } from "../types.js";

// Credentials cannot mint or revoke credentials, and cannot change or delete their workspace.
const DENIED_WORKSPACE_PATHS =
  /^\/(api-keys|playground-credentials|training-tokens)(\/|$)/;

const CREDENTIAL = new RegExp(
  `^Bearer\\s+((?:grad_|${OAUTH_ACCESS_TOKEN_PREFIX})\\S+)$`,
  "i",
);

// A workspace API key or an OAuth access token issued for one workspace.
export const bearerCredential = (headers: Headers): string | undefined =>
  headers.get("authorization")?.match(CREDENTIAL)?.[1] ??
  headers.get("x-api-key") ??
  undefined;

export const isCredentialAllowed = (
  workspaceId: string,
  path: string,
): boolean => {
  const prefix = `/api/v1/workspaces/${workspaceId}`;
  if (path === prefix || path === `${prefix}/`) return false;
  if (!path.startsWith(`${prefix}/`)) return false;

  return !DENIED_WORKSPACE_PATHS.test(path.slice(prefix.length));
};

// The credential acts as its member, the key's creator or the token's user, only inside its workspace.
export const resolveCredentialUser = async (
  credentials: Pick<WorkspaceApiKeyService, "authenticateCredential">,
  request: { headers: Headers; path: string },
): Promise<SessionUser | null> => {
  const secret = bearerCredential(request.headers);
  if (!secret) return null;

  const owner = await credentials.authenticateCredential(secret);
  if (!owner || !isCredentialAllowed(owner.workspaceId, request.path))
    return null;

  return { ...owner.user, impersonatedBy: null, impersonationExpiresAt: null };
};
