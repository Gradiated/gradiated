import { randomUUID } from "node:crypto";

import { afterAll, beforeAll, describe, expect, it } from "vitest";

import { BalanceSourceConflictError } from "../src/billing/ledger.js";
import {
  createBillingService,
  type BillingService,
} from "../src/billing/service.js";
import { type OrganizationRole } from "../src/db/schema/index.js";
import { ControlServiceError } from "../src/errors.js";
import {
  billingAccountRow,
  ledgerRows,
  seedMember,
  seedOrganization,
  seedUser,
} from "./support/fixtures.js";
import { createTestDatabase, type TestDatabase } from "./support/postgres.js";

describe("billing", () => {
  let testDatabase: TestDatabase;
  let billing: BillingService;

  beforeAll(async () => {
    testDatabase = await createTestDatabase();
    billing = createBillingService(testDatabase.database);
  });

  afterAll(() => testDatabase.dispose());

  const prepaidOrganization = () =>
    seedOrganization(testDatabase.database, {
      billing: { mode: "prepaid", balance: 0n },
    });

  const topUp = (
    organizationId: string,
    amount: bigint,
    sourceId: string = randomUUID(),
    stripeCustomerId?: string,
  ) =>
    billing.applyBalanceTransaction({
      organizationId,
      type: "topup",
      amount,
      sourceType: "stripe_checkout_session",
      sourceId,
      createdBy: null,
      ...(stripeCustomerId === undefined ? {} : { stripeCustomerId }),
    });

  const account = (organizationId: string) =>
    billingAccountRow(testDatabase.database, organizationId);

  const ledger = (organizationId: string) =>
    ledgerRows(testDatabase.database, organizationId);

  it("applies a source once and returns the first row on replay", async () => {
    const organizationId = await prepaidOrganization();
    const sourceId = randomUUID();

    const first = await topUp(organizationId, 700n, sourceId);
    const replay = await topUp(organizationId, 700n, sourceId);

    expect(replay).toEqual(first);
    expect(first).toMatchObject({ amount: 700n, balanceAfter: 700n });
    expect(await ledger(organizationId)).toHaveLength(1);
    expect((await account(organizationId))?.balance).toBe(700n);
  });

  it("rejects a replayed source with a different amount", async () => {
    const organizationId = await prepaidOrganization();
    const sourceId = randomUUID();
    await topUp(organizationId, 700n, sourceId);

    await expect(topUp(organizationId, 900n, sourceId)).rejects.toMatchObject({
      name: "BalanceSourceConflictError",
      sourceType: "stripe_checkout_session",
      sourceId,
    });

    expect(await ledger(organizationId)).toHaveLength(1);
    expect((await account(organizationId))?.balance).toBe(700n);
  });

  it("rejects a replayed source for another organization", async () => {
    const owner = await prepaidOrganization();
    const other = await prepaidOrganization();
    const sourceId = randomUUID();
    await topUp(owner, 700n, sourceId);

    await expect(topUp(other, 700n, sourceId)).rejects.toBeInstanceOf(
      BalanceSourceConflictError,
    );

    expect(await ledger(other)).toEqual([]);
    expect((await account(owner))?.balance).toBe(700n);
    expect((await account(other))?.balance).toBe(0n);
  });

  it("records the Stripe customer only when the account has none", async () => {
    const organizationId = await prepaidOrganization();

    await topUp(organizationId, 1n, randomUUID(), `cus_${organizationId}_a`);
    await topUp(organizationId, 1n, randomUUID(), `cus_${organizationId}_b`);

    expect((await account(organizationId))?.stripeCustomerId).toBe(
      `cus_${organizationId}_a`,
    );
  });

  it("rejects a posting without a billing account and writes nothing", async () => {
    const organizationId = await seedOrganization(testDatabase.database);

    const posting = topUp(organizationId, 100n);

    await expect(posting).rejects.toBeInstanceOf(ControlServiceError);
    await expect(posting).rejects.toMatchObject({ code: "not_found" });
    expect(await ledger(organizationId)).toEqual([]);
  });

  it("serializes concurrent postings into a gap-free balance chain", async () => {
    const organizationId = await prepaidOrganization();
    const amounts = Array.from({ length: 20 }, (_, index) =>
      BigInt((index + 1) * 10),
    );

    await Promise.all(amounts.map((amount) => topUp(organizationId, amount)));

    const rows = await ledger(organizationId);
    const total = amounts.reduce((sum, amount) => sum + amount, 0n);
    let expected = 0n;

    for (const row of rows) {
      expected += row.amount;
      expect(row.balanceAfter).toBe(expected);
    }

    expect(rows).toHaveLength(amounts.length);
    expect(expected).toBe(total);
    expect((await account(organizationId))?.balance).toBe(total);
  });

  describe("reads", () => {
    const billedOrganizationWith = (
      role: OrganizationRole,
      status: "active" | "suspended" = "active",
    ) =>
      seedMember(testDatabase.database, {
        role,
        organization: { status, billing: { mode: "prepaid", balance: 0n } },
      });

    const reads = (userId: string, organizationId: string) => [
      () => billing.getBillingAccount(userId, organizationId),
      () => billing.listBalanceTransactions(userId, organizationId),
    ];

    it.each(["owner", "admin", "billing"] as const)(
      "lets a %s read the account and the ledger",
      async (role) => {
        const { userId, organizationId } = await billedOrganizationWith(role);
        await topUp(organizationId, 700n);

        expect(
          await billing.getBillingAccount(userId, organizationId),
        ).toMatchObject({ organizationId, balance: 700n });
        expect(
          await billing.listBalanceTransactions(userId, organizationId),
        ).toMatchObject([{ organizationId, amount: 700n }]);
      },
    );

    it.each([
      ["a member", "member", "active"],
      ["an owner of a suspended organization", "owner", "suspended"],
    ] as const)("forbids %s", async (_name, role, status) => {
      const { userId, organizationId } = await billedOrganizationWith(
        role,
        status,
      );

      for (const read of reads(userId, organizationId)) {
        await expect(read()).rejects.toMatchObject({ code: "forbidden" });
      }
    });

    it("hides the organization from a non-member", async () => {
      const { organizationId } = await billedOrganizationWith("owner");
      const outsider = await seedUser(testDatabase.database);

      for (const read of reads(outsider, organizationId)) {
        await expect(read()).rejects.toMatchObject({ code: "not_found" });
      }
    });

    it("reports a missing billing account as not found", async () => {
      const { userId, organizationId } = await seedMember(
        testDatabase.database,
        { role: "owner" },
      );

      await expect(
        billing.getBillingAccount(userId, organizationId),
      ).rejects.toMatchObject({
        code: "not_found",
        message: "The billing account was not found.",
      });
    });

    it("lists the newest 50 transactions first", async () => {
      const { userId, organizationId } = await billedOrganizationWith("owner");

      for (let amount = 1n; amount <= 51n; amount += 1n) {
        await topUp(organizationId, amount);
      }

      const listed = await billing.listBalanceTransactions(
        userId,
        organizationId,
      );

      expect(listed).toHaveLength(50);
      expect(listed[0]?.amount).toBe(51n);
      expect(listed.at(-1)?.amount).toBe(2n);
    });
  });
});
