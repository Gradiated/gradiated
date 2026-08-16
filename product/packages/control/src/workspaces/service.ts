import { createHash, randomBytes } from "node:crypto";

import { and, asc, eq, isNull } from "drizzle-orm";
import { v7 as uuidv7 } from "uuid";

import type { ControlDatabase } from "../db/client.js";
import {
  apiKeys,
  type ModelPropertiesRecord,
  organizationMembers,
  organizations,
  workspaces,
} from "../db/schema/index.js";

export interface WorkspaceRecord {
  id: string;
  organizationId: string;
  name: string;
  isDefault: boolean;
  archivedAt: Date | null;
  createdAt: Date;
  updatedAt: Date;
}

export interface ApiKeyRecord {
  id: string;
  organizationId: string;
  workspaceId: string;
  name: string;
  expiresAt: Date | null;
  revokedAt: Date | null;
  createdBy: string | null;
  createdAt: Date;
  updatedAt: Date;
}

export interface CreatedApiKey {
  apiKey: ApiKeyRecord;
  secret: string;
}

export interface CredentialSnapshot {
  apiKeyId: string;
  organizationId: string;
  workspaceId: string;
  expiresAt: Date | null;
  revokedAt: Date | null;
}

export interface ServingProjector {
  projectAccount(snapshot: {
    organizationId: string;
    organizationKind: "customer" | "distribution_channel";
    organizationStatus: "active" | "suspended";
    billingMode: "prepaid" | "invoiced";
    balance: bigint;
  }): Promise<void>;
  projectWorkspace(workspace: WorkspaceRecord): Promise<void>;
  projectCredential(
    digestHex: string,
    snapshot: CredentialSnapshot,
  ): Promise<void>;
  projectModel(model: {
    id: string;
    name: string;
    status: "available" | "unavailable" | "retired";
    properties: ModelPropertiesRecord;
  }): Promise<void>;
  applyBalanceTransaction(input: {
    organizationId: string;
    transactionId: string;
    amount: bigint;
  }): Promise<void>;
}

export class ControlServiceError extends Error {
  constructor(
    readonly code: "forbidden" | "not_found" | "unavailable",
    message: string,
    override readonly cause?: unknown,
  ) {
    super(message);
    this.name = "ControlServiceError";
  }
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

type WorkspaceAccess = WorkspaceRecord & {
  organizationStatus: string;
  role: string;
};

export function createWorkspaceApiKeyService(
  database: ControlDatabase,
  projector: ServingProjector,
): WorkspaceApiKeyService {
  async function getWorkspaceAccess(
    userId: string,
    organizationId: string,
    workspaceId: string,
  ): Promise<WorkspaceAccess> {
    const [row] = await database
      .select({
        id: workspaces.id,
        organizationId: workspaces.organizationId,
        name: workspaces.name,
        isDefault: workspaces.isDefault,
        archivedAt: workspaces.archivedAt,
        createdAt: workspaces.createdAt,
        updatedAt: workspaces.updatedAt,
        organizationStatus: organizations.status,
        role: organizationMembers.role,
      })
      .from(workspaces)
      .innerJoin(organizations, eq(organizations.id, workspaces.organizationId))
      .innerJoin(
        organizationMembers,
        and(
          eq(organizationMembers.organizationId, organizations.id),
          eq(organizationMembers.userId, userId),
          eq(organizationMembers.status, "active"),
        ),
      )
      .where(
        and(
          eq(workspaces.id, workspaceId),
          eq(workspaces.organizationId, organizationId),
          eq(organizations.kind, "customer"),
        ),
      )
      .limit(1);

    if (!row) {
      throw new ControlServiceError(
        "not_found",
        "The workspace does not exist or is not accessible.",
      );
    }
    return row;
  }

  async function requireWorkspaceManager(
    userId: string,
    organizationId: string,
  ): Promise<void> {
    const [access] = await database
      .select({
        organizationStatus: organizations.status,
        role: organizationMembers.role,
      })
      .from(organizations)
      .innerJoin(
        organizationMembers,
        and(
          eq(organizationMembers.organizationId, organizations.id),
          eq(organizationMembers.userId, userId),
          eq(organizationMembers.status, "active"),
        ),
      )
      .where(
        and(
          eq(organizations.id, organizationId),
          eq(organizations.kind, "customer"),
        ),
      )
      .limit(1);

    if (!access) {
      throw new ControlServiceError(
        "not_found",
        "The organization does not exist or is not accessible.",
      );
    }
    if (
      access.organizationStatus !== "active" ||
      (access.role !== "owner" && access.role !== "admin")
    ) {
      throw new ControlServiceError(
        "forbidden",
        "Only active organization owners and admins can create workspaces.",
      );
    }
  }

  function requireKeyManager(access: WorkspaceAccess): void {
    if (access.role !== "owner" && access.role !== "admin") {
      throw new ControlServiceError(
        "forbidden",
        "Only organization owners and admins can manage API keys.",
      );
    }
    if (access.organizationStatus !== "active" || access.archivedAt) {
      throw new ControlServiceError(
        "forbidden",
        "API keys cannot be changed for this workspace.",
      );
    }
  }

  return {
    async listWorkspaces(userId, organizationId, includeArchived) {
      return database
        .select({
          id: workspaces.id,
          organizationId: workspaces.organizationId,
          name: workspaces.name,
          isDefault: workspaces.isDefault,
          archivedAt: workspaces.archivedAt,
          createdAt: workspaces.createdAt,
          updatedAt: workspaces.updatedAt,
        })
        .from(workspaces)
        .innerJoin(
          organizations,
          eq(organizations.id, workspaces.organizationId),
        )
        .innerJoin(
          organizationMembers,
          and(
            eq(organizationMembers.organizationId, organizations.id),
            eq(organizationMembers.userId, userId),
            eq(organizationMembers.status, "active"),
          ),
        )
        .where(
          and(
            eq(workspaces.organizationId, organizationId),
            eq(organizations.kind, "customer"),
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
        archivedAt: null,
        createdAt: now,
        updatedAt: now,
      };
      await database.insert(workspaces).values(workspace);
      return workspace;
    },

    async listApiKeys(userId, organizationId, workspaceId) {
      await getWorkspaceAccess(userId, organizationId, workspaceId);
      return database
        .select({
          id: apiKeys.id,
          organizationId: apiKeys.organizationId,
          workspaceId: apiKeys.workspaceId,
          name: apiKeys.name,
          expiresAt: apiKeys.expiresAt,
          revokedAt: apiKeys.revokedAt,
          createdBy: apiKeys.createdBy,
          createdAt: apiKeys.createdAt,
          updatedAt: apiKeys.updatedAt,
        })
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
      const access = await getWorkspaceAccess(
        userId,
        organizationId,
        workspaceId,
      );
      requireKeyManager(access);

      const now = new Date();
      if (input.expiresAt && input.expiresAt <= now) {
        throw new ControlServiceError(
          "forbidden",
          "API-key expiry must be in the future.",
        );
      }

      const secret = `grad_${randomBytes(32).toString("base64url")}`;
      const digest = createHash("sha256").update(secret).digest();
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

      await database.insert(apiKeys).values({ ...apiKey, digest });

      try {
        await projector.projectWorkspace(access);
        await projector.projectCredential(digest.toString("hex"), {
          apiKeyId: apiKey.id,
          organizationId,
          workspaceId,
          expiresAt: input.expiresAt,
          revokedAt: null,
        });
      } catch (error) {
        throw new ControlServiceError(
          "unavailable",
          "The key was stored but serving state is not yet available.",
          error,
        );
      }

      return { apiKey, secret };
    },

    async revokeApiKey(userId, organizationId, workspaceId, apiKeyId) {
      const access = await getWorkspaceAccess(
        userId,
        organizationId,
        workspaceId,
      );
      requireKeyManager(access);

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

      const revokedAt = apiKey.revokedAt ?? new Date();
      const digestHex = apiKey.digest.toString("hex");
      const blocked = {
        apiKeyId: apiKey.id,
        organizationId,
        workspaceId,
        expiresAt: apiKey.expiresAt,
        revokedAt,
      };

      try {
        await projector.projectCredential(digestHex, blocked);
      } catch (error) {
        throw new ControlServiceError(
          "unavailable",
          "The key could not be blocked in serving state.",
          error,
        );
      }

      if (!apiKey.revokedAt) {
        await database
          .update(apiKeys)
          .set({ revokedAt, updatedAt: revokedAt })
          .where(eq(apiKeys.id, apiKey.id));
      }

      try {
        await projector.projectCredential(digestHex, blocked);
      } catch (error) {
        throw new ControlServiceError(
          "unavailable",
          "The key is blocked, but serving state has not converged.",
          error,
        );
      }
    },
  };
}
