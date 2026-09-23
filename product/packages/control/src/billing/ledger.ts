import { and, eq } from "drizzle-orm";
import type { NodePgQueryResultHKT } from "drizzle-orm/node-postgres";
import type { PgDatabase } from "drizzle-orm/pg-core";
import { v7 as uuidv7 } from "uuid";

import {
  balanceTransactions,
  billingAccounts,
  type schema,
} from "../db/schema/index.js";
import { ControlServiceError } from "../errors.js";
import { requireRow } from "../require-row.js";

export type BalanceTransactionRecord = typeof balanceTransactions.$inferSelect;

export type LedgerExecutor = PgDatabase<NodePgQueryResultHKT, typeof schema>;

type BalanceSourceType = BalanceTransactionRecord["sourceType"];

type BalanceEntryFields = {
  organizationId: string;
  type: BalanceTransactionRecord["type"];
  amount: bigint;
  sourceId: string;
  createdBy: string | null;
};

export type SettlementBalanceEntry = BalanceEntryFields & {
  sourceType: Extract<BalanceSourceType, "generation_settlement_batch">;
  settlement: { periodStart: Date; periodEnd: Date; generationCount: bigint };
};

export type DirectBalanceEntry = BalanceEntryFields & {
  sourceType: Exclude<BalanceSourceType, "generation_settlement_batch">;
  settlement?: never;
};

export type BalanceEntry = SettlementBalanceEntry | DirectBalanceEntry;

export type BalancePosting = {
  transaction: BalanceTransactionRecord;
  replayed: boolean;
};

export class BalanceSourceConflictError extends Error {
  constructor(
    readonly sourceType: BalanceSourceType,
    readonly sourceId: string,
  ) {
    super(
      `Balance source ${sourceType}:${sourceId} was already posted with different values.`,
    );
    this.name = "BalanceSourceConflictError";
  }
}

export const billingAccountNotFound = () =>
  new ControlServiceError("not_found", "The billing account was not found.");

const matches = (existing: BalanceTransactionRecord, entry: BalanceEntry) =>
  existing.organizationId === entry.organizationId &&
  existing.type === entry.type &&
  existing.amount === entry.amount;

// The caller must run this inside a transaction: the account row lock
// serializes postings so each balance_after extends the previous one.
export const postBalanceTransaction = async (
  executor: LedgerExecutor,
  entry: BalanceEntry,
): Promise<BalancePosting> => {
  const [account] = await executor
    .select({ balance: billingAccounts.balance })
    .from(billingAccounts)
    .where(eq(billingAccounts.organizationId, entry.organizationId))
    .for("update")
    .limit(1);
  if (!account) throw billingAccountNotFound();

  const [existing] = await executor
    .select()
    .from(balanceTransactions)
    .where(
      and(
        eq(balanceTransactions.sourceType, entry.sourceType),
        eq(balanceTransactions.sourceId, entry.sourceId),
      ),
    )
    .limit(1);
  if (existing) {
    if (!matches(existing, entry)) {
      throw new BalanceSourceConflictError(entry.sourceType, entry.sourceId);
    }

    return { transaction: existing, replayed: true };
  }

  const now = new Date();
  const balanceAfter = account.balance + entry.amount;

  const transaction = requireRow(
    await executor
      .insert(balanceTransactions)
      .values({
        id: uuidv7(),
        organizationId: entry.organizationId,
        type: entry.type,
        amount: entry.amount,
        balanceAfter,
        sourceType: entry.sourceType,
        sourceId: entry.sourceId,
        periodStart: entry.settlement?.periodStart ?? null,
        periodEnd: entry.settlement?.periodEnd ?? null,
        generationCount: entry.settlement?.generationCount ?? null,
        createdBy: entry.createdBy,
        createdAt: now,
      })
      .returning(),
    "The balance transaction returned no row.",
  );
  await executor
    .update(billingAccounts)
    .set({ balance: balanceAfter, updatedAt: now })
    .where(eq(billingAccounts.organizationId, entry.organizationId));

  return { transaction, replayed: false };
};
