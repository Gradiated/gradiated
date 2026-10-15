import type {
  BillingAccountRecord,
  CatalogBillingService,
} from "@gradiated/control";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { StripeGateway } from "../src/billing/stripe-gateway.js";
import {
  BillingPaymentsError,
  createBillingPaymentsService,
} from "../src/billing/top-ups.js";
import {
  balanceTransactionRecord,
  billingAccountRecord,
  captureServiceLogs,
  notUsed,
  organizationId,
  user,
} from "./support.js";

const checkoutUrl = "https://checkout.stripe.com/c/pay/cs_test_123";

afterEach(() => {
  vi.restoreAllMocks();
});

const createPayments = ({
  gateway = {},
  account = {},
  applyBalanceTransaction: applyCredit,
}: {
  gateway?: Partial<StripeGateway>;
  account?: Partial<BillingAccountRecord>;
  applyBalanceTransaction?: CatalogBillingService["applyBalanceTransaction"];
} = {}) => {
  const createCheckoutSession = vi.fn(
    gateway.createCheckoutSession ?? (async () => ({ url: checkoutUrl })),
  );
  const applyBalanceTransaction = vi.fn(
    applyCredit ?? (async () => balanceTransactionRecord),
  );
  const payments = createBillingPaymentsService({
    gateway: {
      createCheckoutSession,
      constructWebhookEvent:
        gateway.constructWebhookEvent ?? notUsed("constructWebhookEvent"),
    },
    accounts: {
      getManagedBillingAccount: async () => ({
        ...billingAccountRecord,
        balance: 0n,
        ...account,
      }),
      applyBalanceTransaction,
    },
    productUrl: "http://localhost:3000/",
  });

  return { applyBalanceTransaction, createCheckoutSession, payments };
};

const topUp = (amount = 50_000_000_000n) => ({
  userId: user.id,
  userEmail: user.email,
  organizationId,
  amount,
});

const checkoutEvent = (
  session: Record<string, unknown> = {},
  type = "checkout.session.completed",
) => ({
  type,
  data: {
    object: {
      id: "cs_test_123",
      mode: "payment",
      payment_status: "paid",
      currency: "usd",
      amount_total: 5_000,
      customer: "cus_123",
      client_reference_id: organizationId,
      metadata: {
        kind: "balance_topup",
        organization_id: organizationId,
        user_id: user.id,
      },
      ...session,
    },
  },
});

const deliver = (event: unknown) => {
  const context = createPayments({
    gateway: { constructWebhookEvent: () => event },
  });
  const delivery = context.payments.handleWebhook({
    payload: "{}",
    signature: "signed",
  });

  return { ...context, delivery };
};

const credit = (amountCents: number, customerId = "cus_123") => ({
  organizationId,
  type: "topup",
  amount: BigInt(amountCents) * 10_000_000n,
  sourceType: "stripe_checkout_session",
  sourceId: "cs_test_123",
  createdBy: user.id,
  stripeCustomerId: customerId,
});

describe("Stripe top-up checkout", () => {
  it("creates a server-priced Checkout Session", async () => {
    const { createCheckoutSession, payments } = createPayments();

    await expect(payments.createTopUpCheckout(topUp())).resolves.toEqual({
      checkoutUrl,
    });
    expect(createCheckoutSession).toHaveBeenCalledWith({
      amountCents: 5_000,
      organizationId,
      userId: user.id,
      customerId: null,
      customerEmail: user.email,
      successUrl:
        "http://localhost:3000/billing?topup=success&session_id={CHECKOUT_SESSION_ID}",
      cancelUrl: "http://localhost:3000/billing?topup=cancelled",
    });
  });

  it("converts the nano-USD amount to exact cents", async () => {
    const { createCheckoutSession, payments } = createPayments();

    await payments.createTopUpCheckout(topUp(123_450_000_000n));

    expect(createCheckoutSession).toHaveBeenCalledWith(
      expect.objectContaining({ amountCents: 12_345 }),
    );
  });

  it.each([5_000_000_001n, 4_990_000_000n, 10_000_010_000_000n])(
    "refuses %s nano-USD without calling Stripe",
    async (amount) => {
      const { createCheckoutSession, payments } = createPayments();

      await expect(payments.createTopUpCheckout(topUp(amount))).rejects.toThrow(
        RangeError,
      );
      expect(createCheckoutSession).not.toHaveBeenCalled();
    },
  );

  it("reuses the account's Stripe customer", async () => {
    const { createCheckoutSession, payments } = createPayments({
      account: { stripeCustomerId: "cus_existing" },
    });

    await payments.createTopUpCheckout(topUp());

    expect(createCheckoutSession).toHaveBeenCalledWith(
      expect.objectContaining({ customerId: "cus_existing" }),
    );
  });

  it("rejects an invoiced account without calling Stripe", async () => {
    const { createCheckoutSession, payments } = createPayments({
      account: { mode: "invoiced" },
    });

    await expect(payments.createTopUpCheckout(topUp())).rejects.toMatchObject({
      code: "not_prepaid",
    });
    expect(createCheckoutSession).not.toHaveBeenCalled();
  });

  it("reports a Stripe failure as provider_error with its cause", async () => {
    const failure = new Error("stripe down");
    const { payments } = createPayments({
      gateway: {
        createCheckoutSession: async () => {
          throw failure;
        },
      },
    });

    const rejection = await payments
      .createTopUpCheckout(topUp())
      .catch((error: unknown) => error);

    expect(rejection).toBeInstanceOf(BillingPaymentsError);
    expect(rejection).toMatchObject({ code: "provider_error", cause: failure });
  });

  it("reports a missing Checkout URL as provider_error", async () => {
    const { payments } = createPayments({
      gateway: {
        createCheckoutSession: async () => ({ url: null }),
      },
    });

    await expect(payments.createTopUpCheckout(topUp())).rejects.toMatchObject({
      code: "provider_error",
    });
  });
});

describe("Stripe webhook", () => {
  it("credits a paid Checkout Session in nano-USD", async () => {
    const { applyBalanceTransaction, delivery } = deliver(checkoutEvent());

    await delivery;

    expect(applyBalanceTransaction).toHaveBeenCalledWith(credit(5_000));
  });

  it("credits an asynchronous payment success", async () => {
    const { applyBalanceTransaction, delivery } = deliver(
      checkoutEvent({}, "checkout.session.async_payment_succeeded"),
    );

    await delivery;

    expect(applyBalanceTransaction).toHaveBeenCalledWith(credit(5_000));
  });

  it("credits with an expanded customer id", async () => {
    const { applyBalanceTransaction, delivery } = deliver(
      checkoutEvent({ customer: { id: "cus_expanded" } }),
    );

    await delivery;

    expect(applyBalanceTransaction).toHaveBeenCalledWith(
      credit(5_000, "cus_expanded"),
    );
  });

  it.each([500, 1_000_000])(
    "credits the boundary amount of %i cents",
    async (amountCents) => {
      const { applyBalanceTransaction, delivery } = deliver(
        checkoutEvent({ amount_total: amountCents }),
      );

      await delivery;

      expect(applyBalanceTransaction).toHaveBeenCalledWith(credit(amountCents));
    },
  );

  it("credits a replayed event with the same idempotency source", async () => {
    const events = [checkoutEvent(), checkoutEvent()];
    const { applyBalanceTransaction, payments } = createPayments({
      gateway: { constructWebhookEvent: () => events.shift() },
    });

    await payments.handleWebhook({ payload: "{}", signature: "signed" });
    await payments.handleWebhook({ payload: "{}", signature: "signed" });

    expect(applyBalanceTransaction.mock.calls.map(([input]) => input)).toEqual([
      credit(5_000),
      credit(5_000),
    ]);
  });

  it.each([
    {
      name: "an unpaid session",
      event: checkoutEvent({ payment_status: "unpaid" }),
    },
    { name: "an unrelated event", event: { type: "customer.created" } },
    {
      name: "a Checkout Session from another integration",
      event: checkoutEvent({
        mode: "subscription",
        metadata: { kind: "plan" },
      }),
    },
    {
      name: "a Checkout Session without metadata",
      event: checkoutEvent({ metadata: null }),
    },
    { name: "a non-object event", event: null },
  ])("ignores $name", async ({ event }) => {
    const { applyBalanceTransaction, delivery } = deliver(event);

    await expect(delivery).resolves.toBeUndefined();
    expect(applyBalanceTransaction).not.toHaveBeenCalled();
  });

  it("rejects and logs an invalid signature", async () => {
    const logs = captureServiceLogs();
    const { applyBalanceTransaction, payments } = createPayments({
      gateway: {
        constructWebhookEvent: () => {
          throw new Error("bad signature");
        },
      },
    });

    await expect(
      payments.handleWebhook({ payload: "{}", signature: "bad" }),
    ).rejects.toMatchObject({ code: "invalid_webhook" });
    expect(applyBalanceTransaction).not.toHaveBeenCalled();
    expect(logs.events()).toEqual([
      expect.objectContaining({
        level: "warn",
        event: "stripe_webhook_signature_invalid",
        error_type: "Error",
      }),
    ]);
  });

  it("propagates a failed credit so Stripe retries the event", async () => {
    const failure = new Error("ledger unavailable");
    const { payments } = createPayments({
      gateway: { constructWebhookEvent: () => checkoutEvent() },
      applyBalanceTransaction: async () => {
        throw failure;
      },
    });

    await expect(
      payments.handleWebhook({ payload: "{}", signature: "signed" }),
    ).rejects.toBe(failure);
  });

  it.each<{
    name: string;
    session: Record<string, unknown>;
    event: string;
  }>([
    {
      name: "a malformed session",
      session: { mode: "subscription" },
      event: "stripe_topup_rejected_schema",
    },
    {
      name: "incomplete top-up metadata",
      session: { metadata: { kind: "balance_topup" } },
      event: "stripe_topup_rejected_metadata_mismatch",
    },
    {
      name: "a client reference mismatch",
      session: { client_reference_id: "0198ae59-294a-73a9-9d2f-000000000000" },
      event: "stripe_topup_rejected_metadata_mismatch",
    },
    {
      name: "a non-USD currency",
      session: { currency: "eur" },
      event: "stripe_topup_rejected_currency",
    },
    {
      name: "a missing amount",
      session: { amount_total: null },
      event: "stripe_topup_rejected_amount_out_of_range",
    },
    {
      name: "an amount below the minimum",
      session: { amount_total: 499 },
      event: "stripe_topup_rejected_amount_out_of_range",
    },
    {
      name: "an amount above the maximum",
      session: { amount_total: 1_000_001 },
      event: "stripe_topup_rejected_amount_out_of_range",
    },
  ])("rejects and logs $name without crediting", async ({ session, event }) => {
    const logs = captureServiceLogs();
    const { applyBalanceTransaction, delivery } = deliver(
      checkoutEvent(session),
    );

    await expect(delivery).rejects.toMatchObject({ code: "invalid_webhook" });
    expect(applyBalanceTransaction).not.toHaveBeenCalled();

    expect(logs.events()).toEqual([
      expect.objectContaining({ level: "error", event }),
    ]);
    expect(logs.lines().join("\n")).not.toContain(organizationId);
    expect(logs.lines().join("\n")).not.toContain(user.id);
  });
});
