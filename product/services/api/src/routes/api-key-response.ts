import type { ApiKey } from "@gradiated/contracts";
import type { ApiKeyRecord } from "@gradiated/control";

export const apiKeyResponse = (record: ApiKeyRecord): ApiKey => ({
  id: record.id,
  organization_id: record.organizationId,
  workspace_id: record.workspaceId,
  name: record.name,
  expires_at: record.expiresAt?.toISOString() ?? null,
  revoked_at: record.revokedAt?.toISOString() ?? null,
  created_by: record.createdBy,
  created_at: record.createdAt.toISOString(),
  updated_at: record.updatedAt.toISOString(),
});
