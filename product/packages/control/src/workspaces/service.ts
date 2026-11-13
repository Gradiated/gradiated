import { createHash } from "node:crypto";

import { createWorkspaceStore, type CredentialOwnerRecord } from "./store.js";
import {
  DEFAULT_EVALUATION_JUDGE,
  type UpdateWorkspace,
} from "@gradiated/contracts";
import { and, asc, eq, getTableColumns, isNull, sql } from "drizzle-orm";
import { v7 as uuidv7 } from "uuid";

import {
  findMembership,
  isAdmin,
  requireOrganizationAdmin,
  requireWritableWorkspace,
  requireWorkspaceEditor,
  requireWorkspaceMembership,
} from "../access.js";
import type { ControlDatabase } from "../db/client.js";
import { apiKeys, workspaces } from "../db/schema/index.js";
import { ControlServiceError } from "../errors.js";
import { requireRow } from "../require-row.js";
import { apiKeyDigest, generateApiKeySecret } from "./api-key-secret.js";

export type WorkspaceRecord = typeof workspaces.$inferSelect;

export type ApiKeyRecord = Omit<typeof apiKeys.$inferSelect, "digest">;

const PLAYGROUND_CREDENTIAL_NAME = "Playground";
const MCP_CREDENTIAL_NAME = "MCP";

// Better Auth's OAuth provider adds this prefix to the access tokens it issues.
export const OAUTH_ACCESS_TOKEN_PREFIX = "grado_";

// The provider's default token hash: unpadded base64url SHA-256 of the unprefixed token.
const oauthTokenHash = (token: string) =>
  createHash("sha256").update(token).digest("base64url");

const PLAYGROUND_CREDENTIAL_LIFETIME_MS = 60 * 60 * 1000;

export interface CreatedApiKey {
  apiKey: ApiKeyRecord;
  secret: string;
}

export interface PlaygroundCredentialRecord {
  apiKeyId: string;
  secret: string;
  expiresAt: Date;
}

export interface WorkspaceApiKeyService {
  listWorkspaces(
    userId: string,
    organizationId: string,
    includeArchived: boolean,
  ): Promise<WorkspaceRecord[]>;
  createWorkspace(
    userId: string,
    organizationId: string,
    input: { name: string },
  ): Promise<WorkspaceRecord>;
  updateWorkspace(
    userId: string,
    workspaceId: string,
    input: UpdateWorkspace,
  ): Promise<WorkspaceRecord>;
  archiveWorkspace(userId: string, workspaceId: string): Promise<void>;
  listApiKeys(userId: string, workspaceId: string): Promise<ApiKeyRecord[]>;
  createApiKey(
    userId: string,
    workspaceId: string,
    input: { name: string; expiresAt: Date | null },
  ): Promise<CreatedApiKey>;
  createPlaygroundCredential(
    userId: string,
    workspaceId: string,
  ): Promise<PlaygroundCredentialRecord>;
  createOAuthInferenceCredential(
    secret: string,
  ): Promise<PlaygroundCredentialRecord | undefined>;
  revokeApiKey(
    userId: string,
    workspaceId: string,
    apiKeyId: string,
  ): Promise<void>;
  authenticateCredential(
    secret: string,
  ): Promise<CredentialOwnerRecord | undefined>;
  describeCredential(secret: string): Promise<
    | (CredentialOwnerRecord & {
        workspaceName: string;
        organizationName: string;
        organizationSlug: string;
      })
    | undefined
  >;
  selectOAuthWorkspace(
    userId: string,
    sessionId: string,
    workspaceId: string,
  ): Promise<void>;
  requirePlaygroundAccess(userId: string, workspaceId: string): Promise<void>;
}

const { digest: _digest, ...apiKeyColumns } = getTableColumns(apiKeys);

const requirePlayground = async (
  database: ControlDatabase,
  userId: string,
  workspaceId: string,
) => {
  const { workspace } = await requireWritableWorkspace(database, {
    userId,
    workspaceId,
  }).catch((error: unknown) => {
    if (error instanceof ControlServiceError && error.code === "forbidden")
      throw new ControlServiceError(
        "forbidden",
        "The playground is unavailable in an archived workspace or a suspended organization.",
      );
    throw error;
  });

  return workspace;
};

export const createWorkspaceApiKeyService = (
  database: ControlDatabase,
  validateEvaluationModel?: (id: string) => Promise<void>,
): WorkspaceApiKeyService => {
  const records = createWorkspaceStore(database);

  // A member's hidden key for one purpose; every call rotates its secret and expiry.
  const createHiddenCredential = async (
    userId: string,
    workspaceId: string,
    name: string,
  ): Promise<PlaygroundCredentialRecord> => {
    const workspace = await requirePlayground(database, userId, workspaceId);

    const now = new Date();
    const expiresAt = new Date(
      now.getTime() + PLAYGROUND_CREDENTIAL_LIFETIME_MS,
    );
    const secret = generateApiKeySecret();
    const digest = apiKeyDigest(secret);

    const apiKey = requireRow(
      await database
        .insert(apiKeys)
        .values({
          id: uuidv7(),
          organizationId: workspace.organizationId,
          workspaceId,
          name,
          digest,
          expiresAt,
          hidden: true,
          createdBy: userId,
          createdAt: now,
          updatedAt: now,
        })
        .onConflictDoUpdate({
          target: [apiKeys.workspaceId, apiKeys.createdBy, apiKeys.name],
          targetWhere: sql`${apiKeys.hidden}`,
          set: { digest, expiresAt, revokedAt: null, updatedAt: now },
        })
        .returning({ id: apiKeys.id }),
      "The hidden key was not saved.",
    );

    return { apiKeyId: apiKey.id, secret, expiresAt };
  };

  // Membership and workspace state are checked by each operation, as for a session.
  const authenticateCredential = async (secret: string) => {
    if (secret.startsWith("grad_"))
      return records.findActiveApiKeyOwner(apiKeyDigest(secret), new Date());
    if (secret.startsWith(OAUTH_ACCESS_TOKEN_PREFIX))
      return records.findActiveOAuthTokenOwner(
        oauthTokenHash(secret.slice(OAUTH_ACCESS_TOKEN_PREFIX.length)),
        new Date(),
      );

    return undefined;
  };

  return {
    async listWorkspaces(userId, organizationId, includeArchived) {
      const membership = await findMembership(database, {
        userId,
        organizationId,
      });
      if (!membership) return [];

      return database
        .select()
        .from(workspaces)
        .where(
          and(
            eq(workspaces.organizationId, organizationId),
            includeArchived ? undefined : isNull(workspaces.archivedAt),
          ),
        )
        .orderBy(asc(workspaces.createdAt), asc(workspaces.id));
    },

    async createWorkspace(userId, organizationId, input) {
      await requireOrganizationAdmin(database, { userId, organizationId });

      const now = new Date();
      const workspace: WorkspaceRecord = {
        id: uuidv7(),
        organizationId,
        name: input.name,
        isDefault: false,
        traceCaptureEnabled: true,
        traceRetentionDays: 180,
        defaultJudgeModel: DEFAULT_EVALUATION_JUDGE,
        archivedAt: null,
        createdAt: now,
        updatedAt: now,
      };

      await database.insert(workspaces).values(workspace);

      return workspace;
    },

    async updateWorkspace(userId, workspaceId, input) {
      await requireWorkspaceEditor(database, { userId, workspaceId });
      if (input.default_judge_model !== undefined)
        await validateEvaluationModel?.(input.default_judge_model);

      return records.update(workspaceId, input);
    },
    async archiveWorkspace(userId, workspaceId) {
      const workspace = await requireWorkspaceEditor(database, {
        userId,
        workspaceId,
      });
      if (workspace.isDefault)
        throw new ControlServiceError(
          "forbidden",
          "The default workspace cannot be deleted.",
        );

      await database
        .update(workspaces)
        .set({
          archivedAt: new Date(),
          traceCaptureEnabled: false,
          updatedAt: new Date(),
        })
        .where(eq(workspaces.id, workspaceId));
    },

    async listApiKeys(userId, workspaceId) {
      await requireWorkspaceMembership(database, {
        userId,
        workspaceId,
      });

      return database
        .select(apiKeyColumns)
        .from(apiKeys)
        .where(
          and(eq(apiKeys.workspaceId, workspaceId), eq(apiKeys.hidden, false)),
        )
        .orderBy(asc(apiKeys.createdAt), asc(apiKeys.id));
    },

    async createApiKey(userId, workspaceId, input) {
      const { workspace } = await requireWritableWorkspace(database, {
        userId,
        workspaceId,
      });

      const now = new Date();
      if (input.expiresAt && input.expiresAt <= now) {
        throw new ControlServiceError(
          "forbidden",
          "API-key expiry must be in the future.",
        );
      }

      const secret = generateApiKeySecret();
      const apiKey: ApiKeyRecord = {
        id: uuidv7(),
        organizationId: workspace.organizationId,
        workspaceId,
        name: input.name,
        expiresAt: input.expiresAt,
        revokedAt: null,
        hidden: false,
        createdBy: userId,
        createdAt: now,
        updatedAt: now,
      };

      await database
        .insert(apiKeys)
        .values({ ...apiKey, digest: apiKeyDigest(secret) });

      return { apiKey, secret };
    },

    // Signed-in members try models without managing keys. Each member has one
    // hidden key per workspace; every call rotates its secret and expiry.
    createPlaygroundCredential: (userId, workspaceId) =>
      createHiddenCredential(userId, workspaceId, PLAYGROUND_CREDENTIAL_NAME),

    // The gateway takes only API keys, so an OAuth client gets a hidden key of its member's.
    async createOAuthInferenceCredential(secret) {
      const owner = await authenticateCredential(secret);
      if (owner?.credential !== "oauth_token") return undefined;

      return createHiddenCredential(
        owner.user.id,
        owner.workspaceId,
        MCP_CREDENTIAL_NAME,
      );
    },

    async revokeApiKey(userId, workspaceId, apiKeyId) {
      const { membership } = await requireWritableWorkspace(database, {
        userId,
        workspaceId,
      });

      const [apiKey] = await database
        .select()
        .from(apiKeys)
        .where(
          and(eq(apiKeys.id, apiKeyId), eq(apiKeys.workspaceId, workspaceId)),
        )
        .limit(1);
      if (!apiKey) {
        throw new ControlServiceError(
          "not_found",
          "The API key was not found.",
        );
      }
      if (!isAdmin(membership.role) && apiKey.createdBy !== userId)
        throw new ControlServiceError(
          "forbidden",
          "Only admins can revoke API keys created by someone else.",
        );

      // Revocation is a row update. The gateway stops accepting the key within
      // its record cache lifetime, so nothing has to be blocked ahead of it.
      if (!apiKey.revokedAt) {
        const revokedAt = new Date();
        await database
          .update(apiKeys)
          .set({ revokedAt, updatedAt: revokedAt })
          .where(eq(apiKeys.id, apiKey.id));
      }
    },

    async requirePlaygroundAccess(userId, workspaceId) {
      await requirePlayground(database, userId, workspaceId);
    },

    authenticateCredential,

    async describeCredential(secret) {
      const owner = await authenticateCredential(secret);
      const names =
        owner && (await records.findWorkspaceNames(owner.workspaceId));

      return owner && names && { ...owner, ...names };
    },

    async selectOAuthWorkspace(userId, sessionId, workspaceId) {
      await requireWritableWorkspace(database, { userId, workspaceId });

      const selected = await records.setSessionOAuthWorkspace(
        sessionId,
        userId,
        workspaceId,
      );
      if (!selected)
        throw new ControlServiceError(
          "not_found",
          "The session was not found.",
        );
    },
  };
};
