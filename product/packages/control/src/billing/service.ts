import type { BalanceTransactionQuery } from "@gradiated/contracts";
import { and, eq, isNull } from "drizzle-orm";

import { requireMembership, requireOrganizationAdmin } from "../access.js";
import type { ControlDatabase } from "../db/client.js";
import { billingAccounts } from "../db/schema/index.js";
import { ControlServiceError } from "../errors.js";
import {
  billingAccountNotFound,
  postBalanceTransaction,
  type DirectBalanceEntry,
  type BalanceTransactionRecord,
} from "./ledger.js";
import { listBalanceTransactionPage } from "./store.js";

export type BillingAccountRecord = typeof billingAccounts.$inferSelect;

export interface BillingService {
  getBillingAccount(
    userId: string,
    organizationId: string,
  ): Promise<BillingAccountRecord>;
  getManagedBillingAccount(
    userId: string,
    organizationId: string,
  ): Promise<BillingAccountRecord>;
  listBalanceTransactions(
    userId: string,
    organizationId: string,
    query?: Partial<BalanceTransactionQuery>,
  ): Promise<{ data: BalanceTransactionRecord[]; nextCursor: string | null }>;
  applyBalanceTransaction(
    input: DirectBalanceEntry & {
      stripeCustomerId?: string | null;
    },
  ): Promise<BalanceTransactionRecord>;
}

export const createBillingService = (
  database: ControlDatabase,
): BillingService => {
  const account = async (organizationId: string) => {
    const [row] = await database
      .select()
      .from(billingAccounts)
      .where(eq(billingAccounts.organizationId, organizationId))
      .limit(1);
    if (!row) throw billingAccountNotFound();

    return row;
  };

  const requireBillingReader = async (
    userId: string,
    organizationId: string,
  ) => {
    const membership = await requireMembership(database, {
      userId,
      organizationId,
    });
    if (membership.organizationStatus !== "active")
      throw new ControlServiceError(
        "forbidden",
        "This organization's billing is unavailable.",
      );
  };

  return {
    async getBillingAccount(userId, organizationId) {
      await requireBillingReader(userId, organizationId);

      return account(organizationId);
    },

    async getManagedBillingAccount(userId, organizationId) {
      await requireOrganizationAdmin(database, { userId, organizationId });

      return account(organizationId);
    },

    async listBalanceTransactions(userId, organizationId, query = {}) {
      await requireBillingReader(userId, organizationId);

      return listBalanceTransactionPage(database, organizationId, query);
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
