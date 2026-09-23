import { randomUUID } from "node:crypto";

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { BalanceSourceConflictError } from "../src/billing/ledger.js";
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
