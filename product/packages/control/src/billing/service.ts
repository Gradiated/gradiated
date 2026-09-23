import { and, desc, eq, isNull } from "drizzle-orm";

import { requireMembership } from "../access.js";
import type { ControlDatabase } from "../db/client.js";
import {
  balanceTransactions,
  billingAccounts,
  type OrganizationRole,
} from "../db/schema/index.js";
import { ControlServiceError } from "../errors.js";
import {
  billingAccountNotFound,
  postBalanceTransaction,
  type DirectBalanceEntry,
  type BalanceTransactionRecord,
} from "./ledger.js";

export type BillingAccountRecord = typeof billingAccounts.$inferSelect;

export interface BillingService {
  getBillingAccount(
    userId: string,
    organizationId: string,
  ): Promise<BillingAccountRecord>;
  listBalanceTransactions(
    userId: string,
    organizationId: string,
  ): Promise<BalanceTransactionRecord[]>;
  applyBalanceTransaction(
    input: DirectBalanceEntry & {
      stripeCustomerId?: string | null;
    },
  ): Promise<BalanceTransactionRecord>;
}

const billingRoles: ReadonlySet<OrganizationRole> = new Set([
  "owner",
  "admin",
  "billing",
]);

export const createBillingService = (
  database: ControlDatabase,
): BillingService => {
  const requireBillingAccess = async (
    userId: string,
    organizationId: string,
  ) => {
    const membership = await requireMembership(database, {
      userId,
      organizationId,
    });
    if (
      membership.organizationStatus !== "active" ||
      !billingRoles.has(membership.role)
    ) {
      throw new ControlServiceError(
        "forbidden",
        "The current member cannot view billing for this organization.",
      );
    }
  };

  return {
    async getBillingAccount(userId, organizationId) {
      await requireBillingAccess(userId, organizationId);

      const [account] = await database
        .select()
        .from(billingAccounts)
        .where(eq(billingAccounts.organizationId, organizationId))
        .limit(1);
      if (!account) throw billingAccountNotFound();

      return account;
    },

    async listBalanceTransactions(userId, organizationId) {
      await requireBillingAccess(userId, organizationId);

      return database
        .select()
        .from(balanceTransactions)
        .where(eq(balanceTransactions.organizationId, organizationId))
        .orderBy(
          desc(balanceTransactions.createdAt),
          desc(balanceTransactions.id),
        )
        .limit(50);
    },

    async applyBalanceTransaction({ stripeCustomerId, ...entry }) {
      return database.transaction(async (transaction) => {
        const posting = await postBalanceTransaction(transaction, entry);

        if (stripeCustomerId) {
          await transaction
            .update(billingAccounts)
            .set({ stripeCustomerId, updatedAt: new Date() })
            .where(
              and(
                eq(billingAccounts.organizationId, entry.organizationId),
                isNull(billingAccounts.stripeCustomerId),
              ),
            );
        }

        return posting.transaction;
      });
    },
  };
};
