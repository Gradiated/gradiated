import { and, eq, inArray, max } from "drizzle-orm";
import { drizzle } from "drizzle-orm/node-postgres";
import type { Pool, PoolClient } from "pg";
import { z } from "zod";

import {
  postBalanceTransaction,
  type LedgerExecutor,
} from "../billing/ledger.js";
import {
  balanceTransactions,
  billingAccounts,
  schema,
} from "../db/schema/index.js";
import { settlementSourceId } from "./slot.js";

const advisoryLockName = "gradiated-generation-settlement-v1";

const acquiredRowSchema = z.object({ acquired: z.boolean() });
const unlockedRowSchema = z.object({ unlocked: z.boolean() });
const settlementSourceType = "generation_settlement_batch";

export type SettlementPosting = {
  generationCount: bigint;
  organizationId: string;
  periodEnd: Date;
  periodStart: Date;
  slotId: string;
  totalCharge: bigint;
};

export type SettlementLeadership = {
  getBillingOrganizationIds(organizationIds: string[]): Promise<Set<string>>;
  getExistingSourceIds(sourceIds: string[]): Promise<Set<string>>;
  getLatestSettlementPeriodStart(): Promise<Date | null>;
  postSettlement(posting: SettlementPosting): Promise<boolean>;
  release(): Promise<void>;
};

export type GenerationSettlementStore = {
  tryAcquireLeadership(): Promise<SettlementLeadership | null>;
};

// Passing an error to PoolClient.release destroys the connection. The advisory
// lock is session-scoped, so a connection that may still hold it must never
// return to the pool.
const destroy = (client: PoolClient, error: unknown): void => {
  client.release(error instanceof Error ? error : true);
};

class PostgresSettlementLeadership implements SettlementLeadership {
  readonly #client: PoolClient;
  readonly #database: LedgerExecutor;
  #released = false;
  #rollbackFailure: { error: unknown } | null = null;

  constructor(client: PoolClient) {
    this.#client = client;
    this.#database = drizzle({ client, schema });
  }

  async getBillingOrganizationIds(
    organizationIds: string[],
  ): Promise<Set<string>> {
    this.#requireUsableConnection();

    if (organizationIds.length === 0) return new Set();

    const rows = await this.#database
      .select({ organizationId: billingAccounts.organizationId })
      .from(billingAccounts)
      .where(inArray(billingAccounts.organizationId, organizationIds));

    return new Set(rows.map((row) => row.organizationId));
  }

  async getExistingSourceIds(sourceIds: string[]): Promise<Set<string>> {
    this.#requireUsableConnection();

    if (sourceIds.length === 0) return new Set();

    const rows = await this.#database
      .select({ sourceId: balanceTransactions.sourceId })
      .from(balanceTransactions)
      .where(
        and(
          eq(balanceTransactions.sourceType, settlementSourceType),
          inArray(balanceTransactions.sourceId, sourceIds),
        ),
      );

    return new Set(rows.map((row) => row.sourceId));
  }

  async getLatestSettlementPeriodStart(): Promise<Date | null> {
    this.#requireUsableConnection();

    const [row] = await this.#database
      .select({ periodStart: max(balanceTransactions.periodStart) })
      .from(balanceTransactions)
      .where(eq(balanceTransactions.sourceType, settlementSourceType));

    return row?.periodStart ?? null;
  }

  async postSettlement(posting: SettlementPosting): Promise<boolean> {
    this.#requireUsableConnection();

    if (posting.totalCharge <= 0n || posting.generationCount <= 0n) {
      throw new Error(
        `Settlement for organization ${posting.organizationId} in slot ${posting.slotId} must have a positive charge and generation count`,
      );
    }

    const sourceId = settlementSourceId(posting.slotId, posting.organizationId);

    await this.#client.query("BEGIN");

    try {
      const posted = await this.#postInTransaction(posting, sourceId);
      await this.#client.query("COMMIT");

      return posted;
    } catch (error) {
      try {
        await this.#client.query("ROLLBACK");
      } catch (rollbackError) {
        this.#rollbackFailure = { error: rollbackError };
        throw new AggregateError(
          [error, rollbackError],
          "The settlement posting failed and its rollback failed.",
        );
      }

      throw error;
    }
  }

  #requireUsableConnection(): void {
    if (this.#rollbackFailure) {
      throw new Error(
        "The settlement connection is unusable after a failed rollback.",
        { cause: this.#rollbackFailure.error },
      );
    }
  }

  async #postInTransaction(
    posting: SettlementPosting,
    sourceId: string,
  ): Promise<boolean> {
    const { replayed } = await postBalanceTransaction(this.#database, {
      organizationId: posting.organizationId,
      type: "usage",
      amount: -posting.totalCharge,
      sourceType: settlementSourceType,
      sourceId,
      createdBy: null,
      settlement: {
        periodStart: posting.periodStart,
        periodEnd: posting.periodEnd,
        generationCount: posting.generationCount,
      },
    });

    return !replayed;
  }

  async release(): Promise<void> {
    if (this.#released) return;

    this.#released = true;

    if (this.#rollbackFailure) {
      destroy(this.#client, this.#rollbackFailure.error);
      return;
    }

    try {
      const result = await this.#client.query(
        "SELECT pg_advisory_unlock(hashtext($1)) AS unlocked",
        [advisoryLockName],
      );
      const [row] = z.tuple([unlockedRowSchema]).parse(result.rows);
      if (!row.unlocked) {
        throw new Error("The settlement advisory lock was not held.");
      }
    } catch (error) {
      destroy(this.#client, error);
      throw error;
    }

    this.#client.release();
  }
}

export const createGenerationSettlementStore = (
  pool: Pool,
): GenerationSettlementStore => ({
  async tryAcquireLeadership() {
    const client = await pool.connect();

    try {
      const result = await client.query(
        "SELECT pg_try_advisory_lock(hashtext($1)) AS acquired",
        [advisoryLockName],
      );
      const [row] = z.tuple([acquiredRowSchema]).parse(result.rows);
      if (!row.acquired) {
        client.release();
        return null;
      }

      return new PostgresSettlementLeadership(client);
    } catch (error) {
      destroy(client, error);
      throw error;
    }
  },
});
