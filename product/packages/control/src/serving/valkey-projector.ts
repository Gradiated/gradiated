import type {
  GatewayCredential,
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
  return redis.error_reply('gateway account is missing or invalid')
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
    async projectAccount(account) {
      await valkey.hSet(`account:{settlement-0}:${account.organizationId}`, {
        organization_id: account.organizationId,
        organization_kind: account.organizationKind,
        organization_status: account.organizationStatus,
        billing_mode: account.billingMode,
        balance: account.balance.toString(),
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
    async projectCredential(digestHex, credential: GatewayCredential) {
      await valkey.set(
        `credential:${digestHex}`,
        JSON.stringify({
          api_key_id: credential.apiKeyId,
          organization_id: credential.organizationId,
          workspace_id: credential.workspaceId,
          expires_at: credential.expiresAt?.toISOString() ?? null,
          revoked_at: credential.revokedAt?.toISOString() ?? null,
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
