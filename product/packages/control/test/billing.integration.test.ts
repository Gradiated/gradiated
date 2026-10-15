import { randomUUID } from "node:crypto";

import { eq, sql } from "drizzle-orm";
import { afterAll, beforeAll, describe, expect, it } from "vitest";

import { BalanceSourceConflictError } from "../src/billing/ledger.js";
import {
  createBillingService,
  type BillingService,
} from "../src/billing/service.js";
import {
  balanceTransactions,
  type OrganizationRole,
} from "../src/db/schema/index.js";
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

  it("applies concurrent deliveries of the same Stripe event exactly once", async () => {
    const organizationId = await prepaidOrganization();
    const sourceId = randomUUID();

    const deliveries = await Promise.all(
      Array.from({ length: 8 }, () => topUp(organizationId, 700n, sourceId)),
    );

    expect(new Set(deliveries.map((row) => row.id)).size).toBe(1);
    expect(await ledger(organizationId)).toEqual([deliveries[0]]);
    expect((await account(organizationId))?.balance).toBe(700n);
  });

  it("commits one winner when concurrent deliveries disagree on the amount", async () => {
    const organizationId = await prepaidOrganization();
    const sourceId = randomUUID();
    const results = await Promise.allSettled([
      topUp(organizationId, 700n, sourceId),
      topUp(organizationId, 900n, sourceId),
    ]);
    const successes = results.filter((result) => result.status === "fulfilled");
    const failures = results.filter((result) => result.status === "rejected");

    expect(successes).toHaveLength(1);
    expect(failures).toHaveLength(1);
    expect(failures[0]?.reason).toBeInstanceOf(BalanceSourceConflictError);
    const winner = successes[0]!.value;
    expect(await ledger(organizationId)).toEqual([winner]);
    expect((await account(organizationId))?.balance).toBe(winner.amount);
  });

  it("rejects a source replay with a different transaction type", async () => {
    const organizationId = await prepaidOrganization();
    const sourceId = randomUUID();
    const first = await topUp(organizationId, 700n, sourceId);

    await expect(
      billing.applyBalanceTransaction({
        organizationId,
        amount: 700n,
        type: "credit",
        sourceType: "stripe_checkout_session",
        sourceId,
        createdBy: null,
      }),
    ).rejects.toBeInstanceOf(BalanceSourceConflictError);

    expect(await ledger(organizationId)).toEqual([first]);
    expect((await account(organizationId))?.balance).toBe(700n);
  });

  it("keeps source IDs independent across source types", async () => {
    const organizationId = await prepaidOrganization();
    const sourceId = randomUUID();
    await topUp(organizationId, 700n, sourceId);
    const refund = await billing.applyBalanceTransaction({
      organizationId,
      amount: -200n,
      type: "refund",
      sourceType: "stripe_refund",
      sourceId,
      createdBy: null,
    });

    expect(refund).toMatchObject({ amount: -200n, balanceAfter: 500n });
    expect(await ledger(organizationId)).toHaveLength(2);
    expect((await account(organizationId))?.balance).toBe(500n);
  });

  it("preserves nanodollar amounts beyond JavaScript's safe integer range", async () => {
    const organizationId = await prepaidOrganization();
    const amount = 9_007_199_254_740_993n;
    await topUp(organizationId, amount);
    await topUp(organizationId, 1n);

    expect(
      (await ledger(organizationId)).map((row) => row.balanceAfter),
    ).toEqual([amount, amount + 1n]);
    expect((await account(organizationId))?.balance).toBe(amount + 1n);
  });

  it("rolls back the ledger and balance when linking a Stripe customer fails, then permits a retry", async () => {
    const owner = await prepaidOrganization();
    const other = await prepaidOrganization();
    const customerId = `cus_${randomUUID()}`;
    await topUp(owner, 100n, randomUUID(), customerId);
    const sourceId = randomUUID();
    const before = await account(other);

    // The real unique constraint fails after the ledger insert and balance update.
    await expect(
      topUp(other, 700n, sourceId, customerId),
    ).rejects.toMatchObject({
      cause: { code: "23505" },
    });
    expect(await ledger(other)).toEqual([]);
    expect(await account(other)).toEqual(before);
    expect((await account(owner))?.balance).toBe(100n);

    const retried = await topUp(other, 700n, sourceId, `cus_${randomUUID()}`);
    expect(await ledger(other)).toEqual([retried]);
    expect((await account(other))?.balance).toBe(700n);
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

    it.each(["admin"] as const)(
      "lets an %s read the account and the ledger",
      async (role) => {
        const { userId, organizationId } = await billedOrganizationWith(role);
        await topUp(organizationId, 700n);

        expect(
          await billing.getBillingAccount(userId, organizationId),
        ).toMatchObject({ organizationId, balance: 700n });
        expect(
          await billing.listBalanceTransactions(userId, organizationId),
        ).toMatchObject({
          data: [{ organizationId, amount: 700n }],
          nextCursor: null,
        });
      },
    );

    it("forbids an admin of a suspended organization", async () => {
      const { userId, organizationId } = await billedOrganizationWith(
        "admin",
        "suspended",
      );

      for (const read of reads(userId, organizationId)) {
        await expect(read()).rejects.toMatchObject({ code: "forbidden" });
      }
    });

    it("lets a member read billing but not manage it", async () => {
      const { userId, organizationId } = await billedOrganizationWith("member");
      await topUp(organizationId, 700n);

      expect(
        await billing.getBillingAccount(userId, organizationId),
      ).toMatchObject({ balance: 700n });
      expect(
        await billing.listBalanceTransactions(userId, organizationId),
      ).toMatchObject({ data: [{ organizationId, amount: 700n }] });
      await expect(
        billing.getManagedBillingAccount(userId, organizationId),
      ).rejects.toMatchObject({ code: "forbidden" });
    });

    it("hides the organization from a non-member", async () => {
      const { organizationId } = await billedOrganizationWith("admin");
      const outsider = await seedUser(testDatabase.database);

      for (const read of reads(outsider, organizationId)) {
        await expect(read()).rejects.toMatchObject({ code: "not_found" });
      }
    });

    it("reports a missing billing account as not found", async () => {
      const { userId, organizationId } = await seedMember(
        testDatabase.database,
        { role: "admin" },
      );

      await expect(
        billing.getBillingAccount(userId, organizationId),
      ).rejects.toMatchObject({
        code: "not_found",
        message: "The billing account was not found.",
      });
    });

    it("paginates identical timestamps without skipping or repeating rows", async () => {
      const { userId, organizationId } = await billedOrganizationWith("admin");
      for (let amount = 1n; amount <= 7n; amount += 1n) {
        await topUp(organizationId, amount);
      }
      await testDatabase.database
        .update(balanceTransactions)
        .set({ createdAt: sql`'2026-08-16T12:00:00.123456Z'::timestamptz` })
        .where(eq(balanceTransactions.organizationId, organizationId));

      const ids: string[] = [];
      let cursor: string | null = null;
      do {
        const page = await billing.listBalanceTransactions(
          userId,
          organizationId,
          { limit: 3, ...(cursor ? { cursor } : {}) },
        );
        ids.push(...page.data.map((row) => row.id));
        cursor = page.nextCursor;
      } while (cursor);

      const expected = await ledger(organizationId);
      expect(ids).toEqual(
        expected
          .map((row) => row.id)
          .sort()
          .reverse(),
      );
      expect(new Set(ids).size).toBe(7);
    });

    it("does not accept another organization's transaction as a cursor", async () => {
      const { userId, organizationId } = await billedOrganizationWith("admin");
      const other = await prepaidOrganization();
      await topUp(organizationId, 1n);
      const foreign = await topUp(other, 1n);

      expect(
        await billing.listBalanceTransactions(userId, organizationId, {
          cursor: foreign.id,
        }),
      ).toEqual({ data: [], nextCursor: null });
    });

    it("lists the newest 50 transactions first", async () => {
      const { userId, organizationId } = await billedOrganizationWith("admin");

      for (let amount = 1n; amount <= 51n; amount += 1n) {
        await topUp(organizationId, amount);
      }

      const listed = await billing.listBalanceTransactions(
        userId,
        organizationId,
      );

      expect(listed.data).toHaveLength(50);
      expect(listed.data[0]?.amount).toBe(51n);
      expect(listed.data.at(-1)?.amount).toBe(2n);
      expect(listed.nextCursor).toBe(listed.data.at(-1)?.id);

      await topUp(organizationId, 52n);
      const next = await billing.listBalanceTransactions(
        userId,
        organizationId,
        { cursor: listed.nextCursor!, limit: 50 },
      );

      expect(next.data.map((row) => row.amount)).toEqual([1n]);
      expect(next.nextCursor).toBeNull();
    });
  });
});
