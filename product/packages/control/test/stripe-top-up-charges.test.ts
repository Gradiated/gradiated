import Stripe from "stripe";
import { describe, expect, it, vi } from "vitest";

import type { TopUpChargeRecord } from "../src/billing/top-up-charges.js";
import {
  createStripeTopUpCharger,
  settleTopUpCharge,
  type TopUpCharger,
} from "../src/billing/stripe-top-up-charges.js";

const now = new Date("2026-10-28T12:00:00.000Z");

const charge = (
  fields: Partial<TopUpChargeRecord> = {},
): TopUpChargeRecord => ({
  id: "0198ae70-68b0-7644-812d-c4bf16a926e5",
  organizationId: "0198ae59-294a-73a9-9d2f-3c8f5e8e1a01",
  reason: "auto_top_up",
  status: "pending",
  amount: 50_000_000_000n,
  stripeCustomerId: "cus_123",
  stripePaymentMethodId: "pm_123",
  stripeInvoiceId: null,
  failure: null,
  requestKey: null,
  createdBy: null,
  createdAt: now,
  updatedAt: now,
  ...fields,
});

const invoice = (status: string, amountPaid = 0) =>
  ({ id: "in_123", status, amount_paid: amountPaid }) as Stripe.Invoice;

const declined = () =>
  new Stripe.errors.StripeCardError({
    type: "card_error",
    code: "card_declined",
    message: "Your card was declined.",
  });

const fakeStripe = (
  overrides: Partial<{
    retrieve: () => Promise<Stripe.Invoice>;
    pay: () => Promise<Stripe.Invoice>;
  }> = {},
) => {
  const calls = {
    create: vi.fn(async () => invoice("draft")),
    retrieve: vi.fn(overrides.retrieve ?? (async () => invoice("open"))),
    item: vi.fn(async () => ({})),
    finalize: vi.fn(async () => invoice("open")),
    pay: vi.fn(overrides.pay ?? (async () => invoice("paid", 5_000))),
    void: vi.fn(async () => invoice("void")),
    del: vi.fn(async () => ({})),
  };
  const stripe = {
    invoices: {
      create: calls.create,
      retrieve: calls.retrieve,
      finalizeInvoice: calls.finalize,
      pay: calls.pay,
      voidInvoice: calls.void,
      del: calls.del,
    },
    invoiceItems: { create: calls.item },
  } as unknown as Stripe;

  return { calls, charger: createStripeTopUpCharger(stripe) };
};

describe("Stripe top-up charger", () => {
  it("charges the saved card through a paid invoice", async () => {
    const { calls, charger } = fakeStripe();
    const onInvoice = vi.fn(async () => undefined);

    await expect(charger.charge(charge(), onInvoice)).resolves.toEqual({
      status: "succeeded",
      stripeInvoiceId: "in_123",
      amount: 50_000_000_000n,
    });
    expect(onInvoice).toHaveBeenCalledWith("in_123");
    expect(calls.item).toHaveBeenCalledWith(
      expect.objectContaining({ amount: 5_000, currency: "usd" }),
      { idempotencyKey: `top-up-charge:${charge().id}:item` },
    );
    expect(calls.pay).toHaveBeenCalledWith(
      "in_123",
      { payment_method: "pm_123", off_session: true },
      { idempotencyKey: `top-up-charge:${charge().id}:pay` },
    );
  });

  it("voids the invoice and reports a decline", async () => {
    const { calls, charger } = fakeStripe({
      pay: async () => {
        throw declined();
      },
    });

    await expect(
      charger.charge(charge(), async () => undefined),
    ).resolves.toEqual({
      status: "failed",
      failure: "Your card was declined.",
      code: "card_declined",
    });
    expect(calls.void).toHaveBeenCalledWith("in_123");
  });

  it("leaves the charge pending when Stripe is unreachable", async () => {
    const outage = new Error("connect ETIMEDOUT");
    const { calls, charger } = fakeStripe({
      pay: async () => {
        throw outage;
      },
    });

    await expect(charger.charge(charge(), async () => undefined)).rejects.toBe(
      outage,
    );
    expect(calls.void).not.toHaveBeenCalled();
  });

  it("resumes an open invoice without creating another", async () => {
    const { calls, charger } = fakeStripe();
    const onInvoice = vi.fn(async () => undefined);

    await charger.charge(charge({ stripeInvoiceId: "in_123" }), onInvoice);

    expect(calls.create).not.toHaveBeenCalled();
    expect(calls.item).not.toHaveBeenCalled();
    expect(onInvoice).not.toHaveBeenCalled();
    expect(calls.pay).toHaveBeenCalledOnce();
  });

  it("does not pay an invoice that is already paid", async () => {
    const { calls, charger } = fakeStripe({
      retrieve: async () => invoice("paid", 5_000),
    });

    await expect(
      charger.charge(
        charge({ stripeInvoiceId: "in_123" }),
        async () => undefined,
      ),
    ).resolves.toMatchObject({ status: "succeeded" });
    expect(calls.pay).not.toHaveBeenCalled();
  });

  it("voids an unpaid invoice when resolving an expired charge", async () => {
    const { calls, charger } = fakeStripe();

    await expect(
      charger.resolve(charge({ stripeInvoiceId: "in_123" })),
    ).resolves.toMatchObject({ status: "failed", code: "expired" });
    expect(calls.void).toHaveBeenCalledWith("in_123");
  });

  it("credits an expired charge whose invoice was paid", async () => {
    const { charger } = fakeStripe({
      retrieve: async () => invoice("paid", 5_000),
    });

    await expect(
      charger.resolve(charge({ stripeInvoiceId: "in_123" })),
    ).resolves.toMatchObject({ status: "succeeded" });
  });
});

describe("settleTopUpCharge", () => {
  const store = () => ({
    recordInvoice: vi.fn(async () => undefined),
    succeed: vi.fn(async () => undefined),
    fail: vi.fn(async () => undefined),
  });

  const charger = (
    outcome: Awaited<ReturnType<TopUpCharger["charge"]>>,
  ): TopUpCharger => ({
    charge: vi.fn(async () => outcome),
    resolve: vi.fn(async () => ({
      status: "failed" as const,
      failure: "The payment could not be confirmed.",
      code: "expired",
    })),
  });

  it("posts a successful charge", async () => {
    const records = store();

    await settleTopUpCharge(
      {
        store: records,
        charger: charger({
          status: "succeeded",
          stripeInvoiceId: "in_123",
          amount: 50_000_000_000n,
        }),
        now,
      },
      charge(),
    );

    expect(records.succeed).toHaveBeenCalledWith({
      chargeId: charge().id,
      stripeInvoiceId: "in_123",
      amount: 50_000_000_000n,
    });
  });

  it("records a failed charge", async () => {
    const records = store();

    await settleTopUpCharge(
      {
        store: records,
        charger: charger({ status: "failed", failure: "No.", code: "x" }),
        now,
      },
      charge(),
    );

    expect(records.fail).toHaveBeenCalledWith({
      chargeId: charge().id,
      failure: "No.",
    });
  });

  it("leaves a processing charge for the webhook", async () => {
    const records = store();

    await settleTopUpCharge(
      {
        store: records,
        charger: charger({ status: "processing", stripeInvoiceId: "in_123" }),
        now,
      },
      charge(),
    );

    expect(records.succeed).not.toHaveBeenCalled();
    expect(records.fail).not.toHaveBeenCalled();
  });

  it("resolves instead of charging once Stripe may have forgotten the keys", async () => {
    const records = store();
    const stale = charger({ status: "processing", stripeInvoiceId: "in_123" });

    const settled = await settleTopUpCharge(
      { store: records, charger: stale, now },
      charge({ createdAt: new Date(now.getTime() - 24 * 60 * 60_000) }),
    );

    expect(stale.charge).not.toHaveBeenCalled();
    expect(settled).toMatchObject({ status: "failed", code: "expired" });
    expect(records.fail).toHaveBeenCalled();
  });
});
