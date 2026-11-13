import { and, arrayContains, eq, gt, isNull, or, sql } from "drizzle-orm";
import { z } from "zod";
import {
  WorkspaceSchema,
  UpdateWorkspaceSchema,
  UuidSchema,
  EvaluationJudgeSchema,
  type UpdateWorkspace,
} from "@gradiated/contracts";
import type { ControlDatabase } from "../db/client.js";
import { ControlServiceError } from "../errors.js";
import {
  apiKeys,
  oauthAccessTokens,
  sessions,
  users,
  workspaces,
} from "../db/schema/index.js";

const WorkspaceRecordSchema = z.object({
  id: UuidSchema,
  organizationId: UuidSchema,
  name: WorkspaceSchema.shape.name,
  isDefault: z.boolean(),
  archivedAt: z.date().nullable(),
  createdAt: z.date(),
  updatedAt: z.date(),
  traceCaptureEnabled: z.boolean(),
  traceRetentionDays: WorkspaceSchema.shape.trace_retention_days,
  defaultJudgeModel: EvaluationJudgeSchema,
});

export const OAUTH_WORKSPACE_SCOPE = "mcp";

const CredentialOwnerRecordSchema = z.object({
  credential: z.enum(["api_key", "oauth_token"]),
  credentialId: UuidSchema,
  organizationId: UuidSchema,
  workspaceId: UuidSchema,
  user: z.object({
    id: UuidSchema,
    name: z.string(),
    email: z.string(),
    emailVerified: z.boolean(),
    isStaff: z.boolean(),
    image: z.string().nullable(),
    createdAt: z.date(),
  }),
});

export type CredentialOwnerRecord = z.infer<typeof CredentialOwnerRecordSchema>;

const ownerColumns = {
  id: users.id,
  name: users.name,
  email: users.email,
  emailVerified: users.emailVerified,
  isStaff: users.isStaff,
  image: users.image,
  createdAt: users.createdAt,
};

export const createWorkspaceStore = (database: ControlDatabase) => ({
  async get(workspaceId: string) {
    const [workspace] = await database
      .select()
      .from(workspaces)
      .where(eq(workspaces.id, UuidSchema.parse(workspaceId)))
      .limit(1);
    return workspace ? WorkspaceRecordSchema.parse(workspace) : undefined;
  },
  async findActiveApiKeyOwner(digest: Buffer, now: Date) {
    const [record] = await database
      .select({
        credentialId: apiKeys.id,
        organizationId: apiKeys.organizationId,
        workspaceId: apiKeys.workspaceId,
        user: ownerColumns,
      })
      .from(apiKeys)
      .innerJoin(users, eq(users.id, apiKeys.createdBy))
      .where(
        and(
          eq(apiKeys.digest, digest),
          isNull(apiKeys.revokedAt),
          or(isNull(apiKeys.expiresAt), gt(apiKeys.expiresAt, now)),
        ),
      )
      .limit(1);

    return record
      ? CredentialOwnerRecordSchema.parse({ ...record, credential: "api_key" })
      : undefined;
  },
  // The OAuth provider stores a hash of the token and the consented workspace as its reference ID.
  async findActiveOAuthTokenOwner(tokenHash: string, now: Date) {
    const [record] = await database
      .select({
        credentialId: oauthAccessTokens.id,
        organizationId: workspaces.organizationId,
        workspaceId: workspaces.id,
        user: ownerColumns,
      })
      .from(oauthAccessTokens)
      .innerJoin(users, eq(users.id, oauthAccessTokens.userId))
      .innerJoin(
        workspaces,
        eq(sql`${workspaces.id}::text`, oauthAccessTokens.referenceId),
      )
      .where(
        and(
          eq(oauthAccessTokens.token, tokenHash),
          isNull(oauthAccessTokens.revoked),
          gt(oauthAccessTokens.expiresAt, now),
          arrayContains(oauthAccessTokens.scopes, [OAUTH_WORKSPACE_SCOPE]),
        ),
      )
      .limit(1);

    return record
      ? CredentialOwnerRecordSchema.parse({
          ...record,
          credential: "oauth_token",
        })
      : undefined;
  },
  async setSessionOAuthWorkspace(
    sessionId: string,
    userId: string,
    workspaceId: string,
  ) {
    const updated = await database
      .update(sessions)
      .set({ oauthWorkspaceId: UuidSchema.parse(workspaceId) })
      .where(and(eq(sessions.id, sessionId), eq(sessions.userId, userId)))
      .returning({ id: sessions.id });

    return updated.length > 0;
  },
  async update(workspaceId: string, input: UpdateWorkspace) {
    const patch = UpdateWorkspaceSchema.parse(input);
    const [workspace] = await database
      .update(workspaces)
      .set({
        name: patch.name,
        traceCaptureEnabled: patch.trace_capture_enabled,
        traceRetentionDays: patch.trace_retention_days,
        defaultJudgeModel: patch.default_judge_model,
        updatedAt: new Date(),
      })
      .where(eq(workspaces.id, workspaceId))
      .returning()
      .catch((error: unknown) => {
        if (isDuplicateName(error))
          throw new ControlServiceError(
            "conflict",
            "A workspace with this name already exists.",
            error,
          );
        throw error;
      });

    return WorkspaceRecordSchema.parse(workspace);
  },
});

const isDuplicateName = (error: unknown): boolean => {
  if (!error || typeof error !== "object") return false;
  if (
    "code" in error &&
    error.code === "23505" &&
    "constraint" in error &&
    error.constraint === "workspaces_organization_name_lower_unique"
  )
    return true;
  return (
    "cause" in error && error.cause !== error && isDuplicateName(error.cause)
  );
};
