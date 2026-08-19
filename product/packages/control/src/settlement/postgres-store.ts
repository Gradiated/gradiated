import type { Pool, PoolClient } from "pg";
import { v7 as uuidv7 } from "uuid";

const advisoryLockName = "gradiated-generation-settlement-v1";

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

class PostgresSettlementLeadership implements SettlementLeadership {
  readonly #client: PoolClient;
  #released = false;

  constructor(client: PoolClient) {
    this.#client = client;
  }

  async getBillingOrganizationIds(
    organizationIds: string[],
  ): Promise<Set<string>> {
    if (organizationIds.length === 0) return new Set();
    const result = await this.#client.query(
      "SELECT organization_id FROM billing_accounts WHERE organization_id = ANY($1::uuid[])",
      [organizationIds],
    );
    return new Set(
      result.rows.map(
        (row: { organization_id: string }) => row.organization_id,
      ),
    );
  }

  async getExistingSourceIds(sourceIds: string[]): Promise<Set<string>> {
    if (sourceIds.length === 0) return new Set();
    const result = await this.#client.query(
      `
        SELECT source_id
        FROM balance_transactions
        WHERE source_type = 'generation_settlement_batch'
          AND source_id = ANY($1::text[])
      `,
      [sourceIds],
    );
    return new Set(
      result.rows.map((row: { source_id: string }) => row.source_id),
    );
  }

  async getLatestSettlementPeriodStart(): Promise<Date | null> {
    const result = await this.#client.query(
      `
        SELECT max(period_start) AS period_start
        FROM balance_transactions
        WHERE source_type = 'generation_settlement_batch'
      `,
    );
    const value = (result.rows[0] as { period_start: Date | null } | undefined)
      ?.period_start;
    return value ?? null;
  }

  async postSettlement(posting: SettlementPosting): Promise<boolean> {
    const sourceId = `${posting.slotId}:${posting.organizationId}`;
    await this.#client.query("BEGIN");
    try {
      const accountResult = await this.#client.query(
        `
          SELECT balance
          FROM billing_accounts
          WHERE organization_id = $1
          FOR UPDATE
        `,
        [posting.organizationId],
      );
      const account = accountResult.rows[0] as { balance: string } | undefined;
      if (!account) {
        throw new Error(
          `Billing account is missing for organization ${posting.organizationId}`,
        );
      }

      const existing = await this.#client.query(
        `
          SELECT 1
          FROM balance_transactions
          WHERE source_type = 'generation_settlement_batch' AND source_id = $1
          LIMIT 1
        `,
        [sourceId],
      );
      if ((existing.rowCount ?? 0) > 0) {
        await this.#client.query("COMMIT");
        return false;
      }

      const amount = -posting.totalCharge;
      const balanceAfter = BigInt(account.balance) + amount;
      const now = new Date();
      await this.#client.query(
        `
          INSERT INTO balance_transactions
            (id, organization_id, type, amount, balance_after, source_type,
             source_id, period_start, period_end, generation_count, created_by,
             created_at)
          VALUES
            ($1, $2, 'usage', $3, $4, 'generation_settlement_batch',
             $5, $6, $7, $8, NULL, $9)
        `,
        [
          uuidv7(),
          posting.organizationId,
          amount.toString(),
          balanceAfter.toString(),
          sourceId,
          posting.periodStart,
          posting.periodEnd,
          posting.generationCount.toString(),
          now,
        ],
      );
      await this.#client.query(
        "UPDATE billing_accounts SET balance = $1, updated_at = $2 WHERE organization_id = $3",
        [balanceAfter.toString(), now, posting.organizationId],
      );
      await this.#client.query("COMMIT");
      return true;
    } catch (error) {
      await this.#client.query("ROLLBACK");
      throw error;
    }
  }

  async release(): Promise<void> {
    if (this.#released) return;
    this.#released = true;
    try {
      await this.#client.query("SELECT pg_advisory_unlock(hashtext($1))", [
        advisoryLockName,
      ]);
    } finally {
      this.#client.release();
    }
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
      const acquired = (result.rows[0] as { acquired: boolean } | undefined)
        ?.acquired;
      if (!acquired) {
        client.release();
        return null;
      }
      return new PostgresSettlementLeadership(client);
    } catch (error) {
      client.release();
      throw error;
    }
  },
});
