import { randomUUID } from "node:crypto";

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import {
  postBalanceTransaction,
  BalanceSourceConflictError,
} from "../src/billing/ledger.js";
import {
  createGenerationSettlementStore,
  type SettlementLeadership,
} from "../src/settlement/postgres-store.js";
import {
  billingAccountRow,
  ledgerRows,
  seedOrganization,
} from "./support/fixtures.js";
import { createTestDatabase, type TestDatabase } from "./support/postgres.js";
import {
  periodEnd,
  periodStart,
  settlementPosting as posting,
  slotId,
} from "./support/settlement.js";

describe("generation settlement store", () => {
  let testDatabase: TestDatabase;
  let leadership: SettlementLeadership;

  beforeEach(async () => {
    testDatabase = await createTestDatabase();

    const acquired = await createGenerationSettlementStore(
      testDatabase.pool,
    ).tryAcquireLeadership();
    if (!acquired) {
      throw new Error("A fresh database has no settlement leader.");
    }

    leadership = acquired;
  });

  afterEach(async () => {
    await leadership.release();
    await testDatabase.dispose();
  });

  const billedOrganization = (balance = 1_000n) =>
    seedOrganization(testDatabase.database, {
      billing: { mode: "prepaid", balance },
    });

  const ledger = (organizationId: string) =>
    ledgerRows(testDatabase.database, organizationId);

  const balance = async (organizationId: string) =>
    (await billingAccountRow(testDatabase.database, organizationId))?.balance;

  it("grants leadership to one store until it is released", async () => {
    const other = createGenerationSettlementStore(testDatabase.pool);

    expect(await other.tryAcquireLeadership()).toBeNull();

    await leadership.release();
    await leadership.release();
    const successor = await other.tryAcquireLeadership();

    expect(successor).not.toBeNull();
    await successor?.release();
  });

  it("posts a usage debit for the settlement period", async () => {
    const organizationId = await billedOrganization();

    expect(await leadership.postSettlement(posting(organizationId))).toBe(true);

    expect(await ledger(organizationId)).toMatchObject([
      {
        type: "usage",
        amount: -250n,
        balanceAfter: 750n,
        sourceType: "generation_settlement_batch",
        sourceId: `${slotId}:${organizationId}`,
        periodStart,
        periodEnd,
        generationCount: 3n,
        createdBy: null,
      },
    ]);
    expect(await balance(organizationId)).toBe(750n);
  });

  it("ignores a replayed posting", async () => {
    const organizationId = await billedOrganization();
    await leadership.postSettlement(posting(organizationId));

    expect(await leadership.postSettlement(posting(organizationId))).toBe(
      false,
    );

    expect(await ledger(organizationId)).toHaveLength(1);
    expect(await balance(organizationId)).toBe(750n);
  });

  it("rejects a replayed posting with a different charge", async () => {
    const organizationId = await billedOrganization();
    await leadership.postSettlement(posting(organizationId));

    await expect(
      leadership.postSettlement({
        ...posting(organizationId),
        totalCharge: 300n,
      }),
    ).rejects.toBeInstanceOf(BalanceSourceConflictError);

    expect(await ledger(organizationId)).toHaveLength(1);
    expect(await balance(organizationId)).toBe(750n);
    expect(await leadership.postSettlement(posting(organizationId))).toBe(
      false,
    );
  });

  it("rejects a posting without a billing account and stays usable", async () => {
    const organizationId = await seedOrganization(testDatabase.database);
    const billed = await billedOrganization();

    await expect(
      leadership.postSettlement(posting(organizationId)),
    ).rejects.toMatchObject({ code: "not_found" });

    expect(await ledger(organizationId)).toEqual([]);
    expect(await leadership.postSettlement(posting(billed))).toBe(true);
  });

  it("rolls back a debit when the billing account update fails and can retry on the same leader", async () => {
    const organizationId = await billedOrganization();
    const before = await billingAccountRow(
      testDatabase.database,
      organizationId,
    );
    // A database trigger fails after the ledger row has been inserted.
    await testDatabase.pool.query(`
      create function reject_balance_update() returns trigger language plpgsql as $$
      begin
        raise exception 'Injected balance update failure';
      end;
      $$;
      create trigger reject_balance_update before update on billing_accounts
        for each row execute function reject_balance_update();
    `);
    try {
      await expect(
        leadership.postSettlement(posting(organizationId)),
      ).rejects.toMatchObject({ cause: { code: "P0001" } });
      expect(await ledger(organizationId)).toEqual([]);
      expect(
        await billingAccountRow(testDatabase.database, organizationId),
      ).toEqual(before);
      expect(await leadership.getLatestSettlementPeriodStart()).toBeNull();
    } finally {
      await testDatabase.pool.query(
        "drop trigger reject_balance_update on billing_accounts; drop function reject_balance_update()",
      );
    }

    expect(await leadership.postSettlement(posting(organizationId))).toBe(true);
    expect(await balance(organizationId)).toBe(750n);
    expect(await ledger(organizationId)).toHaveLength(1);
  });

  it("rolls back an invalid settlement period and leaves leadership usable", async () => {
    const organizationId = await billedOrganization();
    await expect(
      leadership.postSettlement(
        posting(organizationId, { periodEnd: periodStart }),
      ),
    ).rejects.toMatchObject({ cause: { code: "23514" } });
    expect(await balance(organizationId)).toBe(1_000n);
    expect(await ledger(organizationId)).toEqual([]);
    expect(await leadership.postSettlement(posting(organizationId))).toBe(true);
  });

  it("selects the latest settlement period regardless of posting order and ignores other source types", async () => {
    const organizationId = await billedOrganization();
    const later = new Date("2026-08-15T13:00:00.000Z");
    const sourceId = "operator-only";
    await testDatabase.database.transaction((tx) =>
      postBalanceTransaction(tx, {
        organizationId,
        type: "credit",
        amount: 100n,
        sourceType: "operator",
        sourceId,
        createdBy: null,
      }),
    );
    expect(await leadership.getExistingSourceIds([sourceId])).toEqual(
      new Set(),
    );
    expect(await leadership.getLatestSettlementPeriodStart()).toBeNull();

    await leadership.postSettlement(
      posting(organizationId, {
        slotId: "20260815T130000Z-300s-v1",
        periodStart: later,
        periodEnd: new Date("2026-08-15T13:05:00.000Z"),
      }),
    );
    await leadership.postSettlement(posting(organizationId));
    expect(await leadership.getLatestSettlementPeriodStart()).toEqual(later);
    expect(
      await leadership.getExistingSourceIds([
        sourceId,
        `${slotId}:${organizationId}`,
        `20260815T130000Z-300s-v1:${organizationId}`,
      ]),
    ).toEqual(
      new Set([
        `${slotId}:${organizationId}`,
        `20260815T130000Z-300s-v1:${organizationId}`,
      ]),
    );
  });

  it("reads billing accounts, posted sources and the latest period", async () => {
    const billed = await billedOrganization();
    const unbilled = await seedOrganization(testDatabase.database);
    const unposted = `${slotId}:${randomUUID()}`;

    expect(await leadership.getLatestSettlementPeriodStart()).toBeNull();

    await leadership.postSettlement(posting(billed));

    expect(
      await leadership.getBillingOrganizationIds([billed, unbilled]),
    ).toEqual(new Set([billed]));
    expect(
      await leadership.getExistingSourceIds([`${slotId}:${billed}`, unposted]),
    ).toEqual(new Set([`${slotId}:${billed}`]));
    expect(await leadership.getLatestSettlementPeriodStart()).toEqual(
      periodStart,
    );
    expect(await leadership.getBillingOrganizationIds([])).toEqual(new Set());
    expect(await leadership.getExistingSourceIds([])).toEqual(new Set());
  });
});
