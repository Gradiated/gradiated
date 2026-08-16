import type {
  CredentialSnapshot,
  ServingProjector,
  WorkspaceRecord,
} from "../workspaces/service.js";

interface ValkeyWriter {
  set(key: string, value: string): Promise<unknown>;
  hSet(key: string, values: Record<string, string>): Promise<unknown>;
  eval(
    script: string,
    options: { keys: string[]; arguments: string[] },
  ): Promise<unknown>;
}

const applyBalanceTransactionScript = `
local account_type = redis.call('TYPE', KEYS[1]).ok
if account_type ~= 'hash' then
  return redis.error_reply('account snapshot is missing or invalid')
end
local applied_type = redis.call('TYPE', KEYS[2]).ok
if applied_type ~= 'none' and applied_type ~= 'set' then
  return redis.error_reply('applied transaction set is invalid')
end
local added = redis.call('SADD', KEYS[2], ARGV[1])
if added == 1 then
  redis.call('HINCRBY', KEYS[1], 'balance', ARGV[2])
end
return added
`;

export function createValkeyServingProjector(
  valkey: ValkeyWriter,
): ServingProjector {
  return {
    async projectAccount(snapshot) {
      await valkey.hSet(`account:{settlement-0}:${snapshot.organizationId}`, {
        organization_id: snapshot.organizationId,
        organization_kind: snapshot.organizationKind,
        organization_status: snapshot.organizationStatus,
        billing_mode: snapshot.billingMode,
        balance: snapshot.balance.toString(),
      });
    },
    async projectWorkspace(workspace) {
      await valkey.set(
        `workspace:${workspace.id}`,
        JSON.stringify({
          organization_id: workspace.organizationId,
          workspace_id: workspace.id,
          archived_at: workspace.archivedAt?.toISOString() ?? null,
        }),
      );
    },
    async projectCredential(digestHex, snapshot) {
      await valkey.set(
        `credential:${digestHex}`,
        JSON.stringify({
          api_key_id: snapshot.apiKeyId,
          organization_id: snapshot.organizationId,
          workspace_id: snapshot.workspaceId,
          expires_at: snapshot.expiresAt?.toISOString() ?? null,
          revoked_at: snapshot.revokedAt?.toISOString() ?? null,
        }),
      );
    },
    async projectModel(model) {
      await valkey.set(
        `model:${model.id}`,
        JSON.stringify({
          id: model.id,
          name: model.name,
          status: model.status,
          properties: model.properties,
        }),
      );
    },
    async applyBalanceTransaction(input) {
      await valkey.eval(applyBalanceTransactionScript, {
        keys: [
          `account:{settlement-0}:${input.organizationId}`,
          `applied-balance-transactions:{settlement-0}:${input.organizationId}`,
        ],
        arguments: [input.transactionId, input.amount.toString()],
      });
    },
  };
}
