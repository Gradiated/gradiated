import { createWorkspaceStore } from "./store.js";
import {
  DEFAULT_EVALUATION_JUDGE,
  type UpdateWorkspace,
} from "@gradiated/contracts";
import { and, asc, eq, getTableColumns, isNull } from "drizzle-orm";
import { v7 as uuidv7 } from "uuid";

import {
  findMembership,
  managerRoles,
  requireMembership,
  requireWorkspaceEditor,
  requireWorkspaceMembership,
} from "../access.js";
import type { ControlDatabase } from "../db/client.js";
import { apiKeys, workspaces } from "../db/schema/index.js";
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
  revokeApiKey(
    userId: string,
    workspaceId: string,
    apiKeyId: string,
  ): Promise<void>;
}

const { digest: _digest, ...apiKeyColumns } = getTableColumns(apiKeys);

export const createWorkspaceApiKeyService = (
  database: ControlDatabase,
  validateEvaluationModel?: (id: string) => Promise<void>,
): WorkspaceApiKeyService => {
  const records = createWorkspaceStore(database);
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
      !managerRoles.has(membership.role)
    ) {
      throw new ControlServiceError(
        "forbidden",
        "Only active organization owners and admins can create workspaces.",
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
        .where(eq(apiKeys.workspaceId, workspaceId))
        .orderBy(asc(apiKeys.createdAt), asc(apiKeys.id));
    },

    async createApiKey(userId, workspaceId, input) {
      const workspace = await requireWorkspaceEditor(database, {
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
        createdBy: userId,
        createdAt: now,
        updatedAt: now,
      };

      await database
        .insert(apiKeys)
        .values({ ...apiKey, digest: apiKeyDigest(secret) });

      return { apiKey, secret };
    },

    async revokeApiKey(userId, workspaceId, apiKeyId) {
      await requireWorkspaceEditor(database, { userId, workspaceId });

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
