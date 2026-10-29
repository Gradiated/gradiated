import type {
  BalanceTransactionQuery,
  UpdateAutoTopUp,
} from "@gradiated/contracts";

import { requireMembership, requireOrganizationAdmin } from "../access.js";
import type { ControlDatabase } from "../db/client.js";
import { ControlServiceError } from "../errors.js";
import {
  bindStripeCustomer,
  clearCustomerPaymentMethod,
  readBillingAccount,
  savePaymentMethod,
  savedPaymentMethod,
  updateAutoTopUpSettings,
  updateCustomerPaymentMethod,
  type BillingAccountRecord,
} from "./accounts.js";
import {
  postBalanceTransaction,
  type DirectBalanceEntry,
  type BalanceTransactionRecord,
} from "./ledger.js";
import { listBalanceTransactionPage } from "./store.js";
import { topUpStatus, type TopUpStatus } from "./top-up-charges.js";

export type { BillingAccountRecord } from "./accounts.js";

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
  updateAutoTopUp(
    userId: string,
    organizationId: string,
    settings: UpdateAutoTopUp,
  ): Promise<BillingAccountRecord>;
  // Only Stripe IDs are stored; card details are read from Stripe when shown.
  savePaymentMethod(input: {
    organizationId: string;
    stripeCustomerId: string;
    stripePaymentMethodId: string;
    replacing?: string | null;
  }): Promise<boolean>;
  savedPaymentMethod(organizationId: string): Promise<string | null>;
  updateCustomerPaymentMethod(input: {
    stripeCustomerId: string;
    stripePaymentMethodId: string;
  }): Promise<void>;
  clearCustomerPaymentMethod(stripeCustomerId: string): Promise<void>;
  bindStripeCustomer(
    organizationId: string,
    stripeCustomerId: string,
  ): Promise<string>;
  topUpStatus(organizationId: string): Promise<TopUpStatus>;
}

export const createBillingService = (
  database: ControlDatabase,
): BillingService => {
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

      return readBillingAccount(database, organizationId);
    },

    async getManagedBillingAccount(userId, organizationId) {
      await requireOrganizationAdmin(database, { userId, organizationId });

      return readBillingAccount(database, organizationId);
    },

    async listBalanceTransactions(userId, organizationId, query = {}) {
      await requireBillingReader(userId, organizationId);

      return listBalanceTransactionPage(database, organizationId, query);
    },

    async applyBalanceTransaction({ stripeCustomerId, ...entry }) {
      return database.transaction(async (transaction) => {
        const posting = await postBalanceTransaction(transaction, entry);

        if (stripeCustomerId) {
          await bindStripeCustomer(
            transaction,
            entry.organizationId,
            stripeCustomerId,
          );
        }

        return posting.transaction;
      });
    },

    async updateAutoTopUp(userId, organizationId, settings) {
      await requireOrganizationAdmin(database, { userId, organizationId });

      return updateAutoTopUpSettings(database, organizationId, settings);
    },

    savePaymentMethod: (input) => savePaymentMethod(database, input),

    savedPaymentMethod: (organizationId) =>
      savedPaymentMethod(database, organizationId),

    updateCustomerPaymentMethod: (input) =>
      updateCustomerPaymentMethod(database, input),

    clearCustomerPaymentMethod: (stripeCustomerId) =>
      clearCustomerPaymentMethod(database, stripeCustomerId),

    bindStripeCustomer: (organizationId, stripeCustomerId) =>
      bindStripeCustomer(database, organizationId, stripeCustomerId),

    topUpStatus: (organizationId) => topUpStatus(database, organizationId),
  };
};
