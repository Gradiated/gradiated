import { and, desc, eq, ne } from "drizzle-orm";
import { v7 as uuidv7 } from "uuid";

import {
  GatewayModelDeploymentSchema,
  ModelPropertiesInputSchema,
  type ModelDeploymentRelease,
  type ModelPropertiesInput,
} from "@gradiated/contracts";

import type { ControlDatabase } from "../db/client.js";
import {
  balanceTransactions,
  billingAccounts,
  modelDeployments,
  models,
  organizationMembers,
  organizations,
  type ModelPropertiesRecord,
} from "../db/schema/index.js";
import {
  ControlServiceError,
  type ServingProjector,
} from "../workspaces/service.js";

export interface ModelRecord {
  id: string;
  name: string;
  status: "available" | "unavailable" | "retired";
  properties: ModelPropertiesRecord;
  createdAt: Date;
  updatedAt: Date;
}

export interface ModelDeploymentRecord {
  id: string;
  modelId: string;
  status: "available" | "unavailable" | "draining";
  provider: string;
  region: string;
  faultDomain: string;
  serviceUrl: string;
  release: ModelDeploymentRelease;
  createdAt: Date;
  updatedAt: Date;
}

export interface BillingAccountRecord {
  organizationId: string;
  mode: "prepaid" | "invoiced";
  stripeCustomerId: string | null;
  balance: bigint;
  createdAt: Date;
  updatedAt: Date;
}

export interface BalanceTransactionRecord {
  id: string;
  organizationId: string;
  type:
    | "topup"
    | "usage"
    | "refund"
    | "chargeback"
    | "credit"
    | "payment"
    | "adjustment";
  amount: bigint;
  balanceAfter: bigint;
  sourceType:
    | "stripe_checkout_session"
    | "stripe_refund"
    | "stripe_dispute"
    | "generation_settlement_batch"
    | "openrouter_payment"
    | "operator";
  sourceId: string;
  periodStart: Date | null;
  periodEnd: Date | null;
  generationCount: bigint | null;
  createdBy: string | null;
  createdAt: Date;
}

export interface CatalogBillingService {
  listModels(): Promise<ModelRecord[]>;
  getBillingAccount(
    userId: string,
    organizationId: string,
  ): Promise<BillingAccountRecord>;
  listBalanceTransactions(
    userId: string,
    organizationId: string,
  ): Promise<BalanceTransactionRecord[]>;
  upsertModel(input: {
    id: string;
    name: string;
    status: ModelRecord["status"];
    properties: ModelPropertiesInput;
  }): Promise<ModelRecord>;
  upsertModelDeployment(input: {
    id: string;
    modelId: string;
    status: ModelDeploymentRecord["status"];
    provider: string;
    region: string;
    faultDomain: string;
    serviceUrl: string;
    release: ModelDeploymentRelease;
  }): Promise<ModelDeploymentRecord>;
  initializeCurrentAccount(organizationId: string): Promise<void>;
  projectCurrentAccount(organizationId: string): Promise<void>;
  applyBalanceTransaction(input: {
    organizationId: string;
    type: BalanceTransactionRecord["type"];
    amount: bigint;
    sourceType: BalanceTransactionRecord["sourceType"];
    sourceId: string;
    createdBy: string | null;
    stripeCustomerId?: string | null;
    projectToServing?: boolean;
  }): Promise<BalanceTransactionRecord>;
}

export const createCatalogBillingService = (
  database: ControlDatabase,
  projector: ServingProjector,
): CatalogBillingService => {
  const deploymentRecord = (
    row: typeof modelDeployments.$inferSelect,
  ): ModelDeploymentRecord => ({
    ...row,
    status: row.status as ModelDeploymentRecord["status"],
  });

  const projectModel = async (model: ModelRecord): Promise<void> => {
    const deployments = await database
      .select()
      .from(modelDeployments)
      .where(eq(modelDeployments.modelId, model.id))
      .orderBy(modelDeployments.createdAt, modelDeployments.id);
    await projector.projectModel({
      ...model,
      deployments: deployments.map(deploymentRecord),
    });
  };

  const loadModel = async (modelId: string): Promise<ModelRecord> => {
    const [model] = await database
      .select()
      .from(models)
      .where(eq(models.id, modelId))
      .limit(1);
    if (!model) {
      throw new ControlServiceError("not_found", "The model was not found.");
    }
    return { ...model, status: model.status as ModelRecord["status"] };
  };

  const requireBillingAccess = async (
    userId: string,
    organizationId: string,
  ) => {
    const [access] = await database
      .select({
        role: organizationMembers.role,
        organizationStatus: organizations.status,
      })
      .from(organizationMembers)
      .innerJoin(
        organizations,
        eq(organizations.id, organizationMembers.organizationId),
      )
      .where(
        and(
          eq(organizationMembers.userId, userId),
          eq(organizationMembers.organizationId, organizationId),
          eq(organizationMembers.status, "active"),
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
      !["owner", "admin", "billing"].includes(access.role)
    ) {
      throw new ControlServiceError(
        "forbidden",
        "The current member cannot view billing for this organization.",
      );
    }
  };

  const loadGatewayAccount = async (organizationId: string) => {
    const [account] = await database
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
      .where(eq(organizations.id, organizationId))
      .limit(1);

    if (!account) {
      throw new ControlServiceError(
        "not_found",
        "The billing account was not found.",
      );
    }
    return {
      ...account,
      organizationKind: account.organizationKind as
        "customer" | "distribution_channel",
      organizationStatus: account.organizationStatus as "active" | "suspended",
      billingMode: account.billingMode as "prepaid" | "invoiced",
    };
  };

  return {
    async listModels() {
      const rows = await database
        .select()
        .from(models)
        .where(ne(models.status, "retired"))
        .orderBy(models.createdAt, models.id);
      return rows.map((row) => ({
        ...row,
        status: row.status as ModelRecord["status"],
      }));
    },

    async getBillingAccount(userId, organizationId) {
      await requireBillingAccess(userId, organizationId);
      const [account] = await database
        .select()
        .from(billingAccounts)
        .where(eq(billingAccounts.organizationId, organizationId))
        .limit(1);
      if (!account) {
        throw new ControlServiceError(
          "not_found",
          "The billing account was not found.",
        );
      }
      return {
        ...account,
        mode: account.mode as BillingAccountRecord["mode"],
      };
    },

    async listBalanceTransactions(userId, organizationId) {
      await requireBillingAccess(userId, organizationId);
      const rows = await database
        .select()
        .from(balanceTransactions)
        .where(eq(balanceTransactions.organizationId, organizationId))
        .orderBy(
          desc(balanceTransactions.createdAt),
          desc(balanceTransactions.id),
        )
        .limit(50);
      return rows.map((row) => ({
        ...row,
        type: row.type as BalanceTransactionRecord["type"],
        sourceType: row.sourceType as BalanceTransactionRecord["sourceType"],
      }));
    },

    async upsertModel(input) {
      const now = new Date();
      const properties = ModelPropertiesInputSchema.parse(input.properties);
      const [model] = await database
        .insert(models)
        .values({ ...input, properties, createdAt: now, updatedAt: now })
        .onConflictDoUpdate({
          target: models.id,
          set: {
            name: input.name,
            status: input.status,
            properties,
            updatedAt: now,
          },
        })
        .returning();
      if (!model) throw new Error("The model upsert returned no row.");
      const record = {
        ...model,
        status: model.status as ModelRecord["status"],
      };
      await projectModel(record);
      return record;
    },

    async upsertModelDeployment(input) {
      const validated = GatewayModelDeploymentSchema.parse({
        id: input.id,
        status: input.status,
        provider: input.provider,
        region: input.region,
        fault_domain: input.faultDomain,
        service_url: input.serviceUrl,
        release: input.release,
      });
      const now = new Date();
      const [deployment] = await database
        .insert(modelDeployments)
        .values({
          id: validated.id,
          modelId: input.modelId,
          status: validated.status,
          provider: validated.provider,
          region: validated.region,
          faultDomain: validated.fault_domain,
          serviceUrl: validated.service_url,
          release: validated.release,
          createdAt: now,
          updatedAt: now,
        })
        .onConflictDoUpdate({
          target: modelDeployments.id,
          set: {
            status: validated.status,
            provider: validated.provider,
            region: validated.region,
            faultDomain: validated.fault_domain,
            serviceUrl: validated.service_url,
            release: validated.release,
            updatedAt: now,
          },
        })
        .returning();
      if (!deployment)
        throw new Error("The model deployment upsert returned no row.");
      const record = deploymentRecord(deployment);
      await projectModel(await loadModel(record.modelId));
      return record;
    },

    async initializeCurrentAccount(organizationId) {
      await projector.initializeAccount(
        await loadGatewayAccount(organizationId),
      );
    },

    async projectCurrentAccount(organizationId) {
      await projector.projectAccount(await loadGatewayAccount(organizationId));
    },

    async applyBalanceTransaction(input) {
      const result = await database.transaction(async (transaction) => {
        const [account] = await transaction
          .select()
          .from(billingAccounts)
          .where(eq(billingAccounts.organizationId, input.organizationId))
          .for("update")
          .limit(1);
        if (!account) {
          throw new ControlServiceError(
            "not_found",
            "The billing account was not found.",
          );
        }

        if (input.stripeCustomerId && !account.stripeCustomerId) {
          await transaction
            .update(billingAccounts)
            .set({
              stripeCustomerId: input.stripeCustomerId,
              updatedAt: new Date(),
            })
            .where(eq(billingAccounts.organizationId, input.organizationId));
        }

        const [existing] = await transaction
          .select()
          .from(balanceTransactions)
          .where(
            and(
              eq(balanceTransactions.sourceType, input.sourceType),
              eq(balanceTransactions.sourceId, input.sourceId),
            ),
          )
          .limit(1);
        if (existing) return { transaction: existing, created: false };

        const now = new Date();
        const balanceAfter = account.balance + input.amount;
        const [created] = await transaction
          .insert(balanceTransactions)
          .values({
            id: uuidv7(),
            organizationId: input.organizationId,
            type: input.type,
            amount: input.amount,
            balanceAfter,
            sourceType: input.sourceType,
            sourceId: input.sourceId,
            createdBy: input.createdBy,
            createdAt: now,
          })
          .returning();
        if (!created)
          throw new Error("The balance transaction returned no row.");
        await transaction
          .update(billingAccounts)
          .set({ balance: balanceAfter, updatedAt: now })
          .where(eq(billingAccounts.organizationId, input.organizationId));
        return { transaction: created, created: true };
      });

      if (input.projectToServing !== false) {
        await projector.applyBalanceTransaction({
          organizationId: result.transaction.organizationId,
          transactionId: result.transaction.id,
          amount: result.transaction.amount,
        });
      }
      return {
        ...result.transaction,
        type: result.transaction.type as BalanceTransactionRecord["type"],
        sourceType: result.transaction
          .sourceType as BalanceTransactionRecord["sourceType"],
      };
    },
  };
};
