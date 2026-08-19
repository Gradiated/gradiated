import { and, asc, eq, gt, ne, or } from "drizzle-orm";

import type { ControlDatabase } from "../db/client.js";
import {
  apiKeys,
  balanceTransactions,
  billingAccounts,
  modelDeployments,
  models,
  organizations,
  workspaces,
} from "../db/schema/index.js";
import type { ServingProjector } from "../workspaces/service.js";

type AccountProjection = Parameters<ServingProjector["projectAccount"]>[0];
type WorkspaceProjection = Parameters<ServingProjector["projectWorkspace"]>[0];
type ModelProjection = Parameters<ServingProjector["projectModel"]>[0];

export type CredentialProjection = {
  credential: Parameters<ServingProjector["projectCredential"]>[1];
  digestHex: string;
};

export type BalanceProjectionTransaction = {
  amount: bigint;
  createdAt: Date;
  id: string;
  organizationId: string;
};

export type BalanceTransactionCursor = {
  createdAt: Date;
  id: string;
};

export type ServingProjectionSnapshot = {
  accounts: AccountProjection[];
  credentials: CredentialProjection[];
  models: ModelProjection[];
  workspaces: WorkspaceProjection[];
};

export type ServingProjectionReader = {
  getBalanceTransactions(
    after: BalanceTransactionCursor | undefined,
    limit: number,
  ): Promise<BalanceProjectionTransaction[]>;
  getProjectionSnapshot(): Promise<ServingProjectionSnapshot>;
};

export const createServingProjectionReader = (
  database: ControlDatabase,
): ServingProjectionReader => ({
  async getProjectionSnapshot() {
    const [
      accountRows,
      workspaceRows,
      credentialRows,
      modelRows,
      deploymentRows,
    ] = await Promise.all([
      database
        .select({
          organizationId: organizations.id,
          organizationKind: organizations.kind,
          organizationStatus: organizations.status,
          billingMode: billingAccounts.mode,
          balance: billingAccounts.balance,
        })
        .from(organizations)
        .innerJoin(
          billingAccounts,
          eq(billingAccounts.organizationId, organizations.id),
        )
        .orderBy(organizations.id),
      database.select().from(workspaces).orderBy(workspaces.id),
      database
        .select({
          apiKeyId: apiKeys.id,
          digest: apiKeys.digest,
          organizationId: apiKeys.organizationId,
          workspaceId: apiKeys.workspaceId,
          expiresAt: apiKeys.expiresAt,
          revokedAt: apiKeys.revokedAt,
        })
        .from(apiKeys)
        .orderBy(apiKeys.id),
      database.select().from(models).orderBy(models.id),
      database
        .select()
        .from(modelDeployments)
        .orderBy(
          modelDeployments.modelId,
          modelDeployments.createdAt,
          modelDeployments.id,
        ),
    ]);

    const deploymentsByModel = new Map<
      string,
      ModelProjection["deployments"]
    >();
    for (const deployment of deploymentRows) {
      const deployments = deploymentsByModel.get(deployment.modelId) ?? [];
      deployments.push({
        id: deployment.id,
        status:
          deployment.status as ModelProjection["deployments"][number]["status"],
        serviceUrl: deployment.serviceUrl,
        release: deployment.release,
      });
      deploymentsByModel.set(deployment.modelId, deployments);
    }

    return {
      accounts: accountRows.map((account) => ({
        ...account,
        organizationKind:
          account.organizationKind as AccountProjection["organizationKind"],
        organizationStatus:
          account.organizationStatus as AccountProjection["organizationStatus"],
        billingMode: account.billingMode as AccountProjection["billingMode"],
      })),
      workspaces: workspaceRows,
      credentials: credentialRows.map(({ digest, ...credential }) => ({
        digestHex: digest.toString("hex"),
        credential,
      })),
      models: modelRows.map((model) => ({
        id: model.id,
        name: model.name,
        status: model.status as ModelProjection["status"],
        properties: model.properties,
        deployments: deploymentsByModel.get(model.id) ?? [],
      })),
    };
  },

  async getBalanceTransactions(after, limit) {
    const cursorCondition = after
      ? or(
          gt(balanceTransactions.createdAt, after.createdAt),
          and(
            eq(balanceTransactions.createdAt, after.createdAt),
            gt(balanceTransactions.id, after.id),
          ),
        )
      : undefined;
    return database
      .select({
        amount: balanceTransactions.amount,
        createdAt: balanceTransactions.createdAt,
        id: balanceTransactions.id,
        organizationId: balanceTransactions.organizationId,
      })
      .from(balanceTransactions)
      .where(
        and(
          ne(balanceTransactions.sourceType, "generation_settlement_batch"),
          cursorCondition,
        ),
      )
      .orderBy(asc(balanceTransactions.createdAt), asc(balanceTransactions.id))
      .limit(limit);
  },
});
