import { randomUUID } from "node:crypto";

import { eq } from "drizzle-orm";
import { afterAll, beforeAll, describe, expect, it } from "vitest";

import {
  createBillingService,
  type BillingService,
} from "../src/billing/service.js";
import {
  createTopUpChargeStore,
  type TopUpChargeRecord,
  type TopUpChargeStore,
  type OperationalBalanceReader,
} from "../src/billing/top-up-charges.js";
import {
  billingAccounts,
  topUpCharges,
  organizations,
} from "../src/db/schema/index.js";
import {
  billingAccountRow,
  ledgerRows,
  seedOrganization,
  seedUser,
} from "./support/fixtures.js";
import { createTestDatabase, type TestDatabase } from "./support/postgres.js";

const dollars = (amount: number) => BigInt(amount) * 1_000_000_000n;

const postedBalance: OperationalBalanceReader = async () => null;

const limits = () => ({ maxPerHour: 10, now: new Date() });

describe("top-up charges", () => {
  let testDatabase: TestDatabase;
  let store: TopUpChargeStore;
  let billing: BillingService;

  beforeAll(async () => {
    testDatabase = await createTestDatabase();
    store = createTopUpChargeStore(testDatabase.database);
    billing = createBillingService(testDatabase.database);
  });

  afterAll(() => testDatabase.dispose());

  const card = (organizationId: string, suffix = organizationId) => ({
    organizationId,
    stripeCustomerId: `cus_${organizationId}`,
    stripePaymentMethodId: `pm_${suffix}`,
  });

  const organizationWithCard = async (balance: bigint, autoTopUp = true) => {
    const adminId = await seedUser(testDatabase.database);
    const organizationId = await seedOrganization(testDatabase.database, {
      members: [{ userId: adminId, role: "admin" }],
      billing: { mode: "prepaid", balance },
    });

    await billing.savePaymentMethod(card(organizationId));
    if (autoTopUp) {
      await billing.updateAutoTopUp(adminId, organizationId, {
        enabled: true,
        threshold: dollars(10).toString(),
        amount: dollars(50).toString(),
      });
    }

    return { adminId, organizationId };
  };

  const claimed = async (organizationId: string) => {
    const claim = await store.claimAutoTopUp(
      organizationId,
      postedBalance,
      limits(),
    );
    if (claim.status !== "claimed") throw new Error(`Got ${claim.status}`);

    return claim.charge;
  };

  const charges = (organizationId: string) =>
    testDatabase.database
      .select()
      .from(topUpCharges)
      .where(eq(topUpCharges.organizationId, organizationId));

  describe("auto top-up claims", () => {
    it("claims one charge when the posted balance is below the threshold", async () => {
      const { organizationId } = await organizationWithCard(dollars(5));

      expect(await claimed(organizationId)).toMatchObject({
        organizationId,
        reason: "auto_top_up",
        status: "pending",
        amount: dollars(50),
        stripePaymentMethodId: `pm_${organizationId}`,
        createdBy: null,
      });
      await expect(
        store.claimAutoTopUp(organizationId, postedBalance, limits()),
      ).resolves.toEqual({ status: "not_due" });
      expect(await charges(organizationId)).toHaveLength(1);
      expect(await store.listAutoTopUpOrganizationIds()).toContain(
        organizationId,
      );
    });

    it("does not claim at or above the threshold", async () => {
      const { organizationId } = await organizationWithCard(dollars(10));

      await expect(
        store.claimAutoTopUp(organizationId, postedBalance, limits()),
      ).resolves.toEqual({ status: "not_due" });
    });

    it("uses the operational balance and the credits it reads", async () => {
      const { organizationId } = await organizationWithCard(dollars(100));
      await billing.applyBalanceTransaction({
        organizationId,
        type: "topup",
        amount: dollars(1),
        sourceType: "stripe_checkout_session",
        sourceId: randomUUID(),
        createdBy: null,
      });
      let credits: bigint[] = [];

      const claim = await store.claimAutoTopUp(
        organizationId,
        async (_, creditsSince) => {
          credits = (await creditsSince(new Date(0))).map(
            (credit) => credit.amount,
          );

          return dollars(2);
        },
        limits(),
      );

      expect(claim.status).toBe("claimed");
      expect(credits).toEqual([dollars(1)]);
    });

    it("stops claiming after the hourly limit", async () => {
      const { organizationId } = await organizationWithCard(0n);

      for (let index = 0; index < 2; index += 1) {
        const charge = await claimed(organizationId);
        await store.succeed({
          chargeId: charge.id,
          stripeInvoiceId: `in_${randomUUID()}`,
          amount: dollars(50),
        });
        await testDatabase.database
          .update(billingAccounts)
          .set({ balance: 0n })
          .where(eq(billingAccounts.organizationId, organizationId));
      }

      await expect(
        store.claimAutoTopUp(organizationId, postedBalance, {
          maxPerHour: 2,
          now: new Date(),
        }),
      ).resolves.toEqual({ status: "rate_limited" });
    });

    it("abandons unstarted charges of suspended organizations", async () => {
      const { organizationId } = await organizationWithCard(0n);
      const unstarted = await claimed(organizationId);
      await testDatabase.database
        .update(organizations)
        .set({ status: "suspended" })
        .where(eq(organizations.id, organizationId));

      await expect(
        store.abandonInactive(new Date(Date.now() + 60_000)),
      ).resolves.toBe(1);
      expect(
        (await store.listPendingBefore(new Date(Date.now() + 60_000))).map(
          (charge) => charge.id,
        ),
      ).not.toContain(unstarted.id);
    });

    it("skips suspended organizations", async () => {
      const { organizationId } = await organizationWithCard(0n);
      await testDatabase.database
        .update(organizations)
        .set({ status: "suspended" })
        .where(eq(organizations.id, organizationId));

      expect(await store.listAutoTopUpOrganizationIds()).not.toContain(
        organizationId,
      );
      await expect(
        store.claimAutoTopUp(organizationId, postedBalance, limits()),
      ).resolves.toEqual({ status: "not_due" });
    });
  });

  describe("manual top-ups", () => {
    it("claims a charge on the saved card for the user", async () => {
      const { adminId, organizationId } = await organizationWithCard(0n, false);

      await expect(
        store.claimTopUp({
          organizationId,
          userId: adminId,
          amount: dollars(25),
        }),
      ).resolves.toMatchObject({
        charge: {
          reason: "top_up",
          status: "pending",
          amount: dollars(25),
          createdBy: adminId,
        },
        replayed: false,
      });
    });

    it("returns the first charge when a request key is retried", async () => {
      const { adminId, organizationId } = await organizationWithCard(0n, false);
      const request = {
        organizationId,
        userId: adminId,
        amount: dollars(25),
        requestKey: randomUUID(),
      };
      const first = await store.claimTopUp(request);
      await store.succeed({
        chargeId: first.charge.id,
        stripeInvoiceId: "in_first",
        amount: dollars(25),
      });

      const retried = await store.claimTopUp(request);

      expect(retried).toMatchObject({ replayed: true });
      expect(retried.charge).toMatchObject({
        id: first.charge.id,
        status: "succeeded",
      });
      await expect(
        store.claimTopUp({ ...request, amount: dollars(30) }),
      ).rejects.toMatchObject({ code: "conflict" });
    });

    it("keeps a request key's first parameters", async () => {
      const { adminId, organizationId } = await organizationWithCard(0n, false);
      const request = {
        organizationId,
        requestKey: randomUUID(),
        method: "card" as const,
        amount: dollars(25),
        requestedBy: adminId,
        replacesPaymentMethodId: `pm_${organizationId}`,
      };

      const first = await store.recordRequest(request);
      expect(first).toMatchObject(request);
      await expect(
        store.recordRequest({
          ...request,
          method: "checkout",
          amount: dollars(30),
          replacesPaymentMethodId: null,
        }),
      ).resolves.toEqual(first);
    });

    it("reports a pending charge until it settles", async () => {
      const { adminId, organizationId } = await organizationWithCard(0n, false);
      const { charge } = await store.claimTopUp({
        organizationId,
        userId: adminId,
        amount: dollars(25),
      });

      await expect(billing.topUpStatus(organizationId)).resolves.toEqual({
        pending: true,
        autoTopUpFailure: null,
      });
      await store.succeed({
        chargeId: charge.id,
        stripeInvoiceId: `in_${charge.id}`,
        amount: dollars(25),
      });
      await expect(billing.topUpStatus(organizationId)).resolves.toMatchObject({
        pending: false,
      });
    });

    it("refuses a second charge while one is pending", async () => {
      const { adminId, organizationId } = await organizationWithCard(0n, false);
      await store.claimTopUp({
        organizationId,
        userId: adminId,
        amount: dollars(25),
      });

      await expect(
        store.claimTopUp({
          organizationId,
          userId: adminId,
          amount: dollars(25),
        }),
      ).rejects.toMatchObject({ code: "conflict" });
    });

    it("requires a saved card", async () => {
      const userId = await seedUser(testDatabase.database);
      const organizationId = await seedOrganization(testDatabase.database, {
        members: [{ userId, role: "admin" }],
        billing: { mode: "prepaid", balance: 0n },
      });

      await expect(
        store.claimTopUp({ organizationId, userId, amount: dollars(25) }),
      ).rejects.toMatchObject({ code: "conflict" });
    });
  });

  describe("settlement", () => {
    it("posts a paid invoice exactly once", async () => {
      const { organizationId } = await organizationWithCard(0n);
      const charge = await claimed(organizationId);
      const success = {
        chargeId: charge.id,
        stripeInvoiceId: `in_${organizationId}`,
        amount: dollars(50),
      };

      await store.recordInvoice(charge.id, success.stripeInvoiceId);
      await store.succeed(success);
      await store.succeed(success);

      expect(
        (await billingAccountRow(testDatabase.database, organizationId))
          ?.balance,
      ).toBe(dollars(50));
      expect(await ledgerRows(testDatabase.database, organizationId)).toEqual([
        expect.objectContaining({
          type: "topup",
          sourceType: "stripe_invoice",
          sourceId: `in_${organizationId}`,
        }),
      ]);
      expect((await charges(organizationId))[0]).toMatchObject({
        status: "succeeded",
        stripeInvoiceId: `in_${organizationId}`,
      });
    });

    it("rejects a paid amount that differs from the charge", async () => {
      const { organizationId } = await organizationWithCard(0n);
      const charge = await claimed(organizationId);

      await expect(
        store.succeed({
          chargeId: charge.id,
          stripeInvoiceId: `in_${organizationId}`,
          amount: dollars(51),
        }),
      ).rejects.toThrow(/was paid/);
      expect(await ledgerRows(testDatabase.database, organizationId)).toEqual(
        [],
      );
    });

    it("turns auto top-up off when its charge fails", async () => {
      const { adminId, organizationId } = await organizationWithCard(0n);
      const charge = await claimed(organizationId);

      await store.fail({
        chargeId: charge.id,
        failure: "Your card was declined.",
      });

      expect(
        await billingAccountRow(testDatabase.database, organizationId),
      ).toMatchObject({ autoTopUpEnabled: false });
      await expect(billing.topUpStatus(organizationId)).resolves.toEqual({
        pending: false,
        autoTopUpFailure: "Your card was declined.",
      });
      await expect(
        store.claimAutoTopUp(organizationId, postedBalance, limits()),
      ).resolves.toEqual({ status: "not_due" });

      await billing.updateAutoTopUp(adminId, organizationId, { enabled: true });

      const retried = await claimed(organizationId);
      expect(retried.status).toBe("pending");
      await store.succeed({
        chargeId: retried.id,
        stripeInvoiceId: "in_retried",
        amount: retried.amount,
      });
      await expect(billing.topUpStatus(organizationId)).resolves.toMatchObject({
        autoTopUpFailure: null,
      });
    });

    it("stops reporting a failure once the settings are saved again", async () => {
      const { adminId, organizationId } = await organizationWithCard(0n);
      const charge = await claimed(organizationId);
      await store.fail({ chargeId: charge.id, failure: "Declined." });

      await billing.updateAutoTopUp(adminId, organizationId, {
        enabled: false,
      });

      await expect(billing.topUpStatus(organizationId)).resolves.toMatchObject({
        autoTopUpFailure: null,
      });
    });

    it("keeps auto top-up on when a manual top-up fails", async () => {
      const { adminId, organizationId } = await organizationWithCard(
        dollars(100),
      );
      const charge = await store.claimTopUp({
        organizationId,
        userId: adminId,
        amount: dollars(25),
      });

      await store.fail({ chargeId: charge.charge.id, failure: "Declined." });

      expect(
        await billingAccountRow(testDatabase.database, organizationId),
      ).toMatchObject({ autoTopUpEnabled: true });
      await expect(billing.topUpStatus(organizationId)).resolves.toMatchObject({
        autoTopUpFailure: null,
      });
    });

    it("credits a late payment even after the charge failed", async () => {
      const { organizationId } = await organizationWithCard(0n);
      const charge = await claimed(organizationId);
      await store.fail({ chargeId: charge.id, failure: "Timed out." });

      await store.succeed({
        chargeId: charge.id,
        stripeInvoiceId: `in_${organizationId}`,
        amount: dollars(50),
      });

      expect(
        (await billingAccountRow(testDatabase.database, organizationId))
          ?.balance,
      ).toBe(dollars(50));
    });

    it("reports pending charges by age", async () => {
      const { organizationId } = await organizationWithCard(0n);
      const charge: TopUpChargeRecord = await claimed(organizationId);

      expect(await store.listPendingBefore(new Date(0))).not.toContainEqual(
        charge,
      );
      expect(
        await store.listPendingBefore(new Date(Date.now() + 1_000)),
      ).toContainEqual(charge);
      expect(
        (await store.oldestPendingCreatedAt())!.getTime(),
      ).toBeLessThanOrEqual(charge.createdAt.getTime());
    });
  });

  it("refuses to store a malformed invoice id", async () => {
    const { organizationId } = await organizationWithCard(0n);
    const charge = await claimed(organizationId);

    await expect(store.recordInvoice(charge.id, "")).rejects.toThrow();
    expect((await charges(organizationId))[0]?.stripeInvoiceId).toBeNull();
  });

  describe("saved cards", () => {
    it("follows a card changed in the Stripe billing portal", async () => {
      const { organizationId } = await organizationWithCard(0n);

      await billing.updateCustomerPaymentMethod(card(organizationId, "portal"));

      expect(
        await billingAccountRow(testDatabase.database, organizationId),
      ).toMatchObject({ stripePaymentMethodId: "pm_portal" });
      expect((await claimed(organizationId)).stripePaymentMethodId).toBe(
        "pm_portal",
      );
    });

    it("reads the organization's saved card", async () => {
      const { organizationId } = await organizationWithCard(0n);

      await expect(billing.savedPaymentMethod(organizationId)).resolves.toBe(
        `pm_${organizationId}`,
      );
    });

    it("refuses a card from another Stripe customer", async () => {
      const { organizationId } = await organizationWithCard(0n);

      await expect(
        billing.savePaymentMethod({
          ...card(organizationId, "other"),
          stripeCustomerId: "cus_other",
        }),
      ).rejects.toMatchObject({ code: "conflict" });
    });

    it("saves a replacement only while the card it replaces is still saved", async () => {
      const { organizationId } = await organizationWithCard(0n);
      const newer = card(organizationId, "newer");
      await billing.savePaymentMethod(newer);

      await expect(
        billing.savePaymentMethod({
          ...card(organizationId, "late"),
          replacing: `pm_${organizationId}`,
        }),
      ).resolves.toBe(false);
      await expect(
        billing.savePaymentMethod({
          ...card(organizationId, "current"),
          replacing: "pm_newer",
        }),
      ).resolves.toBe(true);
      expect(
        await billingAccountRow(testDatabase.database, organizationId),
      ).toMatchObject({ stripePaymentMethodId: "pm_current" });
    });

    it("treats a retried save of the same card as saved", async () => {
      const { organizationId } = await organizationWithCard(0n);
      const newer = {
        ...card(organizationId, "newer"),
        replacing: `pm_${organizationId}`,
      };

      await expect(billing.savePaymentMethod(newer)).resolves.toBe(true);
      await expect(billing.savePaymentMethod(newer)).resolves.toBe(true);
    });

    it("clears a removed default card and turns auto top-up off", async () => {
      const { organizationId } = await organizationWithCard(0n);

      await billing.clearCustomerPaymentMethod(`cus_${organizationId}`);

      expect(
        await billingAccountRow(testDatabase.database, organizationId),
      ).toMatchObject({ stripePaymentMethodId: null, autoTopUpEnabled: false });
    });

    it("binds one Stripe customer and keeps the first", async () => {
      const adminId = await seedUser(testDatabase.database);
      const organizationId = await seedOrganization(testDatabase.database, {
        members: [{ userId: adminId, role: "admin" }],
        billing: { mode: "prepaid", balance: 0n },
      });

      await expect(
        billing.bindStripeCustomer(organizationId, "cus_first"),
      ).resolves.toBe("cus_first");
      await expect(
        billing.bindStripeCustomer(organizationId, "cus_second"),
      ).resolves.toBe("cus_first");
    });

    it("keeps auto top-up off when a settings update races a decline", async () => {
      const { adminId, organizationId } = await organizationWithCard(0n);
      const charge = await claimed(organizationId);
      await store.fail({ chargeId: charge.id, failure: "Declined." });

      await expect(
        billing.updateAutoTopUp(adminId, organizationId, {
          amount: dollars(30).toString(),
        }),
      ).resolves.toMatchObject({
        autoTopUpEnabled: false,
        autoTopUpAmount: dollars(30),
      });
    });

    it("requires a saved card and a prepaid account to turn auto top-up on", async () => {
      const adminId = await seedUser(testDatabase.database);
      const prepaid = await seedOrganization(testDatabase.database, {
        members: [{ userId: adminId, role: "admin" }],
        billing: { mode: "prepaid", balance: 0n },
      });
      const invoiced = await seedOrganization(testDatabase.database, {
        members: [{ userId: adminId, role: "admin" }],
        billing: { mode: "invoiced", balance: 0n },
      });

      for (const organizationId of [prepaid, invoiced]) {
        await expect(
          billing.updateAutoTopUp(adminId, organizationId, {
            enabled: true,
            threshold: "0",
            amount: dollars(5).toString(),
          }),
        ).rejects.toMatchObject({ code: "conflict" });
      }
    });

    it("updates only the settings a request names", async () => {
      const { adminId, organizationId } = await organizationWithCard(
        dollars(100),
      );

      await expect(
        billing.updateAutoTopUp(adminId, organizationId, {
          amount: dollars(25).toString(),
        }),
      ).resolves.toMatchObject({
        autoTopUpEnabled: true,
        autoTopUpThreshold: dollars(10),
        autoTopUpAmount: dollars(25),
      });
    });

    it("requires a threshold and amount to turn auto top-up on", async () => {
      const { adminId, organizationId } = await organizationWithCard(0n, false);

      await expect(
        billing.updateAutoTopUp(adminId, organizationId, { enabled: true }),
      ).rejects.toMatchObject({ code: "conflict" });
    });
  });
});
