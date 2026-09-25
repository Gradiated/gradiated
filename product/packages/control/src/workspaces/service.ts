import { and, asc, eq, getTableColumns, isNull } from "drizzle-orm";
import { v7 as uuidv7 } from "uuid";

import {
  findMembership,
  requireMembership,
  requireWorkspaceMembership,
} from "../access.js";
import type { ControlDatabase } from "../db/client.js";
import {
  apiKeys,
  workspaces,
  type OrganizationRole,
} from "../db/schema/index.js";
import { ControlServiceError } from "../errors.js";
import { apiKeyDigest, generateApiKeySecret } from "./api-key-secret.js";

export type WorkspaceRecord = typeof workspaces.$inferSelect;

export type ApiKeyRecord = Omit<typeof apiKeys.$inferSelect, "digest">;

export interface CreatedApiKey {
  apiKey: ApiKeyRecord;
  secret: string;
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
  listApiKeys(
    userId: string,
    organizationId: string,
    workspaceId: string,
  ): Promise<ApiKeyRecord[]>;
  createApiKey(
    userId: string,
    organizationId: string,
    workspaceId: string,
    input: { name: string; expiresAt: Date | null },
  ): Promise<CreatedApiKey>;
  revokeApiKey(
    userId: string,
    organizationId: string,
    workspaceId: string,
    apiKeyId: string,
  ): Promise<void>;
}

const keyManagerRoles: ReadonlySet<OrganizationRole> = new Set([
  "owner",
  "admin",
]);

const { digest: _digest, ...apiKeyColumns } = getTableColumns(apiKeys);

export const createWorkspaceApiKeyService = (
  database: ControlDatabase,
): WorkspaceApiKeyService => {
  const requireWorkspaceManager = async (
    userId: string,
    organizationId: string,
  ): Promise<void> => {
    const membership = await requireMembership(database, {
      userId,
      organizationId,
    });
    if (
      membership.organizationStatus !== "active" ||
      !keyManagerRoles.has(membership.role)
    ) {
      throw new ControlServiceError(
        "forbidden",
        "Only active organization owners and admins can create workspaces.",
      );
    }
  };

  const requireKeyManager = async (
    userId: string,
    organizationId: string,
    workspaceId: string,
  ): Promise<void> => {
    const { membership, workspace } = await requireWorkspaceMembership(
      database,
      { userId, organizationId, workspaceId },
    );
    if (!keyManagerRoles.has(membership.role)) {
      throw new ControlServiceError(
        "forbidden",
        "Only organization owners and admins can manage API keys.",
      );
    }
    if (membership.organizationStatus !== "active" || workspace.archivedAt) {
      throw new ControlServiceError(
        "forbidden",
        "API keys cannot be changed for this workspace.",
      );
    }
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
      await requireWorkspaceManager(userId, organizationId);

      const now = new Date();
      const workspace: WorkspaceRecord = {
        id: uuidv7(),
        organizationId,
        name: input.name,
        isDefault: false,
        traceCaptureEnabled: false,
        traceRetentionDays: 30,
        archivedAt: null,
        createdAt: now,
        updatedAt: now,
      };

      await database.insert(workspaces).values(workspace);

      return workspace;
    },

    async listApiKeys(userId, organizationId, workspaceId) {
      await requireWorkspaceMembership(database, {
        userId,
        organizationId,
        workspaceId,
      });

      return database
        .select(apiKeyColumns)
        .from(apiKeys)
        .where(
          and(
            eq(apiKeys.organizationId, organizationId),
            eq(apiKeys.workspaceId, workspaceId),
          ),
        )
        .orderBy(asc(apiKeys.createdAt), asc(apiKeys.id));
    },

    async createApiKey(userId, organizationId, workspaceId, input) {
      await requireKeyManager(userId, organizationId, workspaceId);

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
        organizationId,
        workspaceId,
        name: input.name,
        expiresAt: input.expiresAt,
        revokedAt: null,
        createdBy: userId,
        createdAt: now,
        updatedAt: now,
      };

      await database
        .insert(apiKeys)
        .values({ ...apiKey, digest: apiKeyDigest(secret) });

      return { apiKey, secret };
    },

    async revokeApiKey(userId, organizationId, workspaceId, apiKeyId) {
      await requireKeyManager(userId, organizationId, workspaceId);

      const [apiKey] = await database
        .select()
        .from(apiKeys)
        .where(
          and(
            eq(apiKeys.id, apiKeyId),
            eq(apiKeys.organizationId, organizationId),
            eq(apiKeys.workspaceId, workspaceId),
          ),
        )
        .limit(1);
      if (!apiKey) {
        throw new ControlServiceError(
          "not_found",
          "The API key was not found.",
        );
      }

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
  };
};
