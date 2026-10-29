import { randomUUID } from "node:crypto";

import type {
  TopUpChargeOutcome,
  TopUpChargeRecord,
  TopUpRequest,
  TopUpCharger,
} from "@gradiated/control";
import { ControlServiceError } from "@gradiated/control";
import { describe, expect, it, vi } from "vitest";

import type { SavedCard } from "../src/billing/stripe-gateway.js";
import { createBillingPaymentsService } from "../src/billing/payments.js";
import {
  billingAccountRecord,
  balanceTransactionRecord,
  cardDetailsCache,
  notUsed,
  organizationId,
  user,
} from "./support.js";

const chargeId = "0198ae70-68b0-7644-812d-c4bf16a926e4";
const checkoutUrl = "https://checkout.stripe.com/c/pay/cs_test_topup";
const portalUrl = "https://billing.stripe.com/p/session/test_123";

const card: SavedCard = {
  customerId: "cus_123",
  paymentMethodId: "pm_123",
  brand: "visa",
  last4: "4242",
  expMonth: 8,
  expYear: 2028,
};

const savedCardAccount = {
  stripeCustomerId: "cus_123",
  stripePaymentMethodId: "pm_123",
};

const pendingCharge: TopUpChargeRecord = {
  id: chargeId,
  organizationId,
  reason: "top_up",
  status: "pending",
  amount: 50_000_000_000n,
  stripeCustomerId: "cus_123",
  stripePaymentMethodId: "pm_123",
  stripeInvoiceId: null,
  failure: null,
  requestKey: null,
  createdBy: user.id,
  createdAt: new Date(),
  updatedAt: new Date(),
};

const createPayments = ({
  event,
  account = {},
  savedCard = card,
  outcome = {
    status: "succeeded",
    stripeInvoiceId: "in_123",
    amount: 50_000_000_000n,
  },
  claimTopUp = async () => ({ charge: pendingCharge, replayed: false }),
  saved = true,
  setupOrganizationId = organizationId,
  publishableKey = "pk_test_123",
}: {
  event?: unknown;
  account?: Partial<typeof billingAccountRecord>;
  savedCard?: SavedCard | null;
  outcome?: TopUpChargeOutcome | Error;
  claimTopUp?: () => Promise<{
    charge: TopUpChargeRecord;
    replayed: boolean;
  }>;
  saved?: boolean;
  setupOrganizationId?: string | null;
  publishableKey?: string | null;
} = {}) => {
  const mocks = {
    createCheckoutSession: vi.fn(async () => ({ url: checkoutUrl })),
    createBillingPortalSession: vi.fn(async () => ({ url: portalUrl })),
    createCustomer: vi.fn(async () => ({ customerId: "cus_new" })),
    retrieveDefaultCard: vi.fn(async () => savedCard),
    bindStripeCustomer: vi.fn(
      async (_organizationId: string, customerId: string) => customerId,
    ),
    retrieveCard: vi.fn(async () => savedCard),
    retrievePaymentCard: vi.fn(async () => savedCard),
    createCardSetup: vi.fn(async () => ({ clientSecret: "seti_123_secret" })),
    retrieveCardSetup: vi.fn(async () => ({
      organizationId: setupOrganizationId,
      replacesPaymentMethodId: "pm_old",
      card: savedCard,
    })),
    applyBalanceTransaction: vi.fn(async () => balanceTransactionRecord),
    setDefaultPaymentMethod: vi.fn(async () => undefined),
    savePaymentMethod: vi.fn(async () => saved),
    savedPaymentMethod: vi.fn(
      async (): Promise<string | null> => savedCard?.paymentMethodId ?? null,
    ),
    updateCustomerPaymentMethod: vi.fn(async () => undefined),
    clearCustomerPaymentMethod: vi.fn(async () => undefined),
    claimTopUp: vi.fn(claimTopUp),
    recordRequest: vi.fn(async (request: TopUpRequest) => ({
      ...request,
      createdAt: new Date(),
    })),
    recordInvoice: vi.fn(async () => undefined),
    succeed: vi.fn(async () => undefined),
    fail: vi.fn(async () => undefined),
  };
  const charger: TopUpCharger = {
    charge: vi.fn(async () => {
      if (outcome instanceof Error) throw outcome;

      return outcome;
    }),
    resolve: notUsed("charger.resolve"),
  };
  const payments = createBillingPaymentsService({
    gateway: {
      createCheckoutSession: mocks.createCheckoutSession,
      createBillingPortalSession: mocks.createBillingPortalSession,
      createCustomer: mocks.createCustomer,
      retrieveDefaultCard: mocks.retrieveDefaultCard,
      retrieveCard: mocks.retrieveCard,
      retrievePaymentCard: mocks.retrievePaymentCard,
      createCardSetup: mocks.createCardSetup,
      retrieveCardSetup: mocks.retrieveCardSetup,
      setDefaultPaymentMethod: mocks.setDefaultPaymentMethod,
      constructWebhookEvent: () => event,
    },
    accounts: {
      getManagedBillingAccount: async () => ({
        ...billingAccountRecord,
        ...account,
      }),
      applyBalanceTransaction: mocks.applyBalanceTransaction,
      savePaymentMethod: mocks.savePaymentMethod,
      savedPaymentMethod: mocks.savedPaymentMethod,
      updateCustomerPaymentMethod: mocks.updateCustomerPaymentMethod,
      bindStripeCustomer: mocks.bindStripeCustomer,
      clearCustomerPaymentMethod: mocks.clearCustomerPaymentMethod,
    },
    topUpCharges: {
      claimTopUp: mocks.claimTopUp,
      recordRequest: mocks.recordRequest,
      recordInvoice: mocks.recordInvoice,
      succeed: mocks.succeed,
      fail: mocks.fail,
    },
    charger,
    productUrl: "http://localhost:3000",
    publishableKey: publishableKey ?? undefined,
    cardDetails: cardDetailsCache(),
  });
  const deliver = () =>
    payments.handleWebhook({ payload: "{}", signature: "signed" });

  return { ...mocks, charger, payments, deliver };
};

const caller = { userId: user.id, userEmail: user.email, organizationId };

const topUp = (method?: "card" | "checkout") => ({
  ...caller,
  amount: 50_000_000_000n,
  ...(method ? { method } : {}),
});

describe("top-ups with a saved card", () => {
  it("charges the saved card and reports it paid", async () => {
    const { claimTopUp, succeed, createCheckoutSession, payments } =
      createPayments({ account: savedCardAccount });

    await expect(payments.createTopUp(topUp())).resolves.toEqual({
      status: "paid",
      checkoutUrl: null,
    });
    expect(claimTopUp).toHaveBeenCalledWith({
      organizationId,
      userId: user.id,
      amount: 50_000_000_000n,
    });
    expect(succeed).toHaveBeenCalledWith({
      chargeId,
      stripeInvoiceId: "in_123",
      amount: 50_000_000_000n,
    });
    expect(createCheckoutSession).not.toHaveBeenCalled();
  });

  it("reports a decline with Stripe's message", async () => {
    const { fail, payments } = createPayments({
      account: savedCardAccount,
      outcome: {
        status: "failed",
        failure: "Your card was declined.",
        code: "card_declined",
      },
    });

    await expect(payments.createTopUp(topUp())).rejects.toMatchObject({
      code: "payment_failed",
      message: "Your card was declined.",
    });
    expect(fail).toHaveBeenCalledWith({
      chargeId,
      failure: "Your card was declined.",
    });
  });

  it("leaves the charge for the worker when Stripe is unreachable", async () => {
    const { succeed, fail, payments } = createPayments({
      account: savedCardAccount,
      outcome: new Error("connect ETIMEDOUT"),
    });

    await expect(payments.createTopUp(topUp())).resolves.toEqual({
      status: "processing",
      checkoutUrl: null,
    });
    expect(succeed).not.toHaveBeenCalled();
    expect(fail).not.toHaveBeenCalled();
  });

  it("refuses a second payment while one is in progress", async () => {
    const { payments } = createPayments({
      account: savedCardAccount,
      claimTopUp: async () => {
        throw new ControlServiceError("conflict", "In progress.");
      },
    });

    await expect(payments.createTopUp(topUp())).rejects.toMatchObject({
      code: "conflict",
    });
  });

  it("returns a retried request's first result without charging again", async () => {
    const { charger, payments } = createPayments({
      account: savedCardAccount,
      claimTopUp: async () => ({
        charge: { ...pendingCharge, status: "succeeded" },
        replayed: true,
      }),
    });

    await expect(
      payments.createTopUp({
        ...topUp(),
        requestKey: randomUUID(),
      }),
    ).resolves.toEqual({ status: "paid", checkoutUrl: null });
    expect(charger.charge).not.toHaveBeenCalled();
  });

  it("repeats a card request retried as Checkout with the card", async () => {
    const { claimTopUp, createCheckoutSession, payments, recordRequest } =
      createPayments({
        account: savedCardAccount,
        claimTopUp: async () => ({ charge: pendingCharge, replayed: true }),
      });
    recordRequest.mockImplementation(async (request) => ({
      ...request,
      method: "card",
      createdAt: new Date(),
    }));

    await expect(
      payments.createTopUp({ ...topUp("checkout"), requestKey: "key-1" }),
    ).resolves.toEqual({ status: "processing", checkoutUrl: null });
    expect(recordRequest).toHaveBeenCalledWith({
      organizationId,
      requestKey: "key-1",
      method: "checkout",
      amount: 50_000_000_000n,
      requestedBy: user.id,
      replacesPaymentMethodId: "pm_123",
    });
    expect(claimTopUp).toHaveBeenCalled();
    expect(createCheckoutSession).not.toHaveBeenCalled();
  });

  it("repeats a Checkout request retried after a card was saved", async () => {
    const { claimTopUp, createCheckoutSession, payments, recordRequest } =
      createPayments({ account: savedCardAccount });
    recordRequest.mockImplementation(async (request) => ({
      ...request,
      method: "checkout",
      createdAt: new Date(),
    }));

    await expect(
      payments.createTopUp({ ...topUp(), requestKey: "key-1" }),
    ).resolves.toEqual({ status: "checkout", checkoutUrl });
    expect(createCheckoutSession).toHaveBeenCalledWith(
      expect.objectContaining({ requestKey: "key-1" }),
    );
    expect(claimTopUp).not.toHaveBeenCalled();
  });

  it("resends a Checkout retry's first parameters", async () => {
    const { createCheckoutSession, payments, recordRequest } = createPayments({
      account: savedCardAccount,
    });
    recordRequest.mockImplementation(async (request) => ({
      ...request,
      method: "checkout",
      requestedBy: "0198ae70-0000-7000-8000-000000000001",
      replacesPaymentMethodId: null,
      createdAt: new Date(),
    }));

    await payments.createTopUp({ ...topUp(), requestKey: "key-1" });

    expect(createCheckoutSession).toHaveBeenCalledWith(
      expect.objectContaining({
        userId: "0198ae70-0000-7000-8000-000000000001",
        replacesPaymentMethodId: null,
      }),
    );
  });

  it("refuses a Checkout request key older than Stripe keeps it", async () => {
    const { createCheckoutSession, payments, recordRequest } = createPayments();
    recordRequest.mockImplementation(async (request) => ({
      ...request,
      createdAt: new Date(Date.now() - 24 * 60 * 60_000),
    }));

    await expect(
      payments.createTopUp({ ...topUp(), requestKey: "key-1" }),
    ).rejects.toMatchObject({ code: "conflict" });
    expect(createCheckoutSession).not.toHaveBeenCalled();
  });

  it("refuses a request key reused for another amount", async () => {
    const { charger, createCheckoutSession, payments, recordRequest } =
      createPayments({ account: savedCardAccount });
    recordRequest.mockImplementation(async (request) => ({
      ...request,
      amount: 10_000_000_000n,
      createdAt: new Date(),
    }));

    await expect(
      payments.createTopUp({ ...topUp(), requestKey: "key-1" }),
    ).rejects.toMatchObject({ code: "conflict" });
    expect(charger.charge).not.toHaveBeenCalled();
    expect(createCheckoutSession).not.toHaveBeenCalled();
  });

  it("repeats a retried request's decline", async () => {
    const { payments } = createPayments({
      account: savedCardAccount,
      claimTopUp: async () => ({
        charge: {
          ...pendingCharge,
          status: "failed",
          failure: "Your card was declined.",
        },
        replayed: true,
      }),
    });

    await expect(payments.createTopUp(topUp())).rejects.toMatchObject({
      code: "payment_failed",
      message: "Your card was declined.",
    });
  });

  it("creates one Stripe customer before the first Checkout", async () => {
    const {
      bindStripeCustomer,
      createCheckoutSession,
      createCustomer,
      payments,
    } = createPayments({ account: { stripeCustomerId: null } });

    await payments.createTopUp(topUp("checkout"));

    expect(createCustomer).toHaveBeenCalledWith({
      organizationId,
      email: user.email,
    });
    expect(bindStripeCustomer).toHaveBeenCalledWith(organizationId, "cus_new");
    expect(createCheckoutSession).toHaveBeenCalledWith(
      expect.objectContaining({
        customerId: "cus_new",
        replacesPaymentMethodId: null,
      }),
    );
  });

  it("uses Checkout when asked to, even with a saved card", async () => {
    const { claimTopUp, payments } = createPayments({
      account: savedCardAccount,
    });

    await expect(payments.createTopUp(topUp("checkout"))).resolves.toEqual({
      status: "checkout",
      checkoutUrl,
    });
    expect(claimTopUp).not.toHaveBeenCalled();
  });
});

describe("cards and the billing portal", () => {
  it("starts card entry with a card-only SetupIntent for the customer", async () => {
    const { createCardSetup, payments } = createPayments({
      account: { stripeCustomerId: "cus_existing" },
    });

    await expect(payments.createCardSetup(caller)).resolves.toEqual({
      clientSecret: "seti_123_secret",
      publishableKey: "pk_test_123",
    });
    expect(createCardSetup).toHaveBeenCalledWith({
      organizationId,
      userId: user.id,
      customerId: "cus_existing",
      replacesPaymentMethodId: null,
    });
  });

  it("reports card entry unavailable without a publishable key", async () => {
    const { createCardSetup, payments } = createPayments({
      publishableKey: null,
    });

    await expect(payments.createCardSetup(caller)).rejects.toMatchObject({
      code: "unavailable",
    });
    expect(createCardSetup).not.toHaveBeenCalled();
  });

  it("saves a confirmed card and makes it the default", async () => {
    const {
      payments,
      retrieveCardSetup,
      savePaymentMethod,
      setDefaultPaymentMethod,
    } = createPayments();

    await payments.saveCard({ ...caller, setupIntentId: "seti_123" });

    expect(retrieveCardSetup).toHaveBeenCalledWith("seti_123");
    expect(savePaymentMethod).toHaveBeenCalledWith(
      expect.objectContaining({
        replacing: "pm_old",
        organizationId,
        stripePaymentMethodId: "pm_123",
      }),
    );
    expect(setDefaultPaymentMethod).toHaveBeenCalledWith("cus_123", "pm_123");
  });

  it("does not let a delayed save replace a newer card", async () => {
    const { payments, setDefaultPaymentMethod } = createPayments({
      saved: false,
    });

    await payments.saveCard({ ...caller, setupIntentId: "seti_123" });

    expect(setDefaultPaymentMethod).not.toHaveBeenCalled();
  });

  it("points Stripe at a card saved while the default was being set", async () => {
    const { payments, savedPaymentMethod, setDefaultPaymentMethod } =
      createPayments();
    savedPaymentMethod.mockResolvedValue("pm_newer");

    await payments.saveCard({ ...caller, setupIntentId: "seti_123" });

    expect(setDefaultPaymentMethod.mock.calls).toEqual([
      ["cus_123", "pm_123"],
      ["cus_123", "pm_newer"],
    ]);
  });

  it.each([
    [
      "another organization's SetupIntent",
      { setupOrganizationId: "0198ae70-0000-7000-8000-000000000000" },
    ],
    ["an unconfirmed SetupIntent", { savedCard: null }],
  ])("refuses to save %s", async (_, options) => {
    const { payments, savePaymentMethod } = createPayments(options);

    await expect(
      payments.saveCard({ ...caller, setupIntentId: "seti_123" }),
    ).rejects.toMatchObject({ code: "card_not_confirmed" });
    expect(savePaymentMethod).not.toHaveBeenCalled();
  });

  it("reads card details from Stripe once and then from the cache", async () => {
    const { payments, retrieveCard } = createPayments();

    const first = await payments.describeCard("pm_123");
    const second = await payments.describeCard("pm_123");

    expect(first).toEqual({
      brand: "visa",
      last4: "4242",
      expMonth: 8,
      expYear: 2028,
    });
    expect(second).toEqual(first);
    expect(retrieveCard).toHaveBeenCalledOnce();
  });

  it("has no card details when Stripe cannot be reached", async () => {
    const { payments, retrieveCard } = createPayments();
    retrieveCard.mockRejectedValueOnce(new Error("Stripe is down"));

    await expect(payments.describeCard("pm_123")).resolves.toBeNull();
  });

  it("opens the billing portal for invoices", async () => {
    const { createBillingPortalSession, payments } = createPayments({
      account: savedCardAccount,
    });

    await expect(payments.createPaymentMethodSession(caller)).resolves.toEqual({
      url: portalUrl,
    });
    expect(createBillingPortalSession).toHaveBeenCalledWith({
      customerId: "cus_123",
      returnUrl: "http://localhost:3000/billing",
    });
  });

  it("has no billing portal before the first payment", async () => {
    const { createBillingPortalSession, payments } = createPayments({
      account: { stripeCustomerId: null },
    });

    await expect(
      payments.createPaymentMethodSession(caller),
    ).rejects.toMatchObject({ code: "no_billing_customer" });
    expect(createBillingPortalSession).not.toHaveBeenCalled();
  });

  it("rejects an invoiced account", async () => {
    const { payments } = createPayments({ account: { mode: "invoiced" } });

    await expect(
      payments.createPaymentMethodSession(caller),
    ).rejects.toMatchObject({ code: "not_prepaid" });
  });
});

describe("card webhooks", () => {
  const invoiceEvent = (
    invoice: Record<string, unknown> = {},
    kind = "top_up_charge",
  ) => ({
    type: "invoice.paid",
    data: {
      object: {
        id: "in_123",
        currency: "usd",
        amount_paid: 5_000,
        metadata: { kind, top_up_charge_id: chargeId },
        ...invoice,
      },
    },
  });

  const topUpEvent = (session: Record<string, unknown> = {}) => ({
    type: "checkout.session.completed",
    data: {
      object: {
        id: "cs_test_topup",
        mode: "payment",
        payment_status: "paid",
        currency: "usd",
        amount_total: 5_000,
        customer: "cus_123",
        payment_intent: "pi_123",
        client_reference_id: organizationId,
        metadata: {
          kind: "balance_topup",
          organization_id: organizationId,
          user_id: user.id,
          replaces_payment_method: "",
        },
        ...session,
      },
    },
  });

  it("saves the card a Checkout top-up paid with and makes it the default", async () => {
    const {
      applyBalanceTransaction,
      deliver,
      retrievePaymentCard,
      savePaymentMethod,
      setDefaultPaymentMethod,
    } = createPayments({ event: topUpEvent() });

    await deliver();

    expect(applyBalanceTransaction).toHaveBeenCalledOnce();
    expect(retrievePaymentCard).toHaveBeenCalledWith("pi_123");
    expect(savePaymentMethod).toHaveBeenCalledWith({
      organizationId,
      stripeCustomerId: "cus_123",
      stripePaymentMethodId: "pm_123",
      replacing: null,
    });
    expect(setDefaultPaymentMethod).toHaveBeenCalledWith("cus_123", "pm_123");
  });

  it("keeps a card saved after Checkout opened when its event arrives late", async () => {
    const {
      applyBalanceTransaction,
      deliver,
      savePaymentMethod,
      setDefaultPaymentMethod,
    } = createPayments({
      event: topUpEvent({
        metadata: {
          kind: "balance_topup",
          organization_id: organizationId,
          user_id: user.id,
          replaces_payment_method: "pm_old",
        },
      }),
      saved: false,
    });

    await deliver();

    expect(applyBalanceTransaction).toHaveBeenCalledOnce();
    expect(savePaymentMethod).toHaveBeenCalledWith(
      expect.objectContaining({ replacing: "pm_old" }),
    );
    expect(setDefaultPaymentMethod).not.toHaveBeenCalled();
  });

  it("credits a top-up whose payment kept no card without saving one", async () => {
    const { applyBalanceTransaction, deliver, savePaymentMethod } =
      createPayments({ event: topUpEvent(), savedCard: null });

    await deliver();

    expect(applyBalanceTransaction).toHaveBeenCalledOnce();
    expect(savePaymentMethod).not.toHaveBeenCalled();
  });

  it("follows the default card a customer picks in the portal", async () => {
    const { deliver, retrieveDefaultCard, updateCustomerPaymentMethod } =
      createPayments({
        event: {
          type: "customer.updated",
          data: {
            object: {
              id: "cus_123",
              invoice_settings: { default_payment_method: "pm_123" },
            },
          },
        },
      });

    await deliver();

    expect(retrieveDefaultCard).toHaveBeenCalledWith("cus_123");
    expect(updateCustomerPaymentMethod).toHaveBeenCalledWith({
      stripeCustomerId: "cus_123",
      stripePaymentMethodId: "pm_123",
    });
  });

  it("rewrites the default when it changed during the write", async () => {
    const { deliver, retrieveDefaultCard, updateCustomerPaymentMethod } =
      createPayments({
        event: {
          type: "customer.updated",
          data: {
            object: {
              id: "cus_123",
              invoice_settings: { default_payment_method: "pm_123" },
            },
          },
        },
      });
    retrieveDefaultCard
      .mockResolvedValueOnce(card)
      .mockResolvedValue({ ...card, paymentMethodId: "pm_newer" });

    await deliver();

    expect(updateCustomerPaymentMethod.mock.calls).toEqual([
      [{ stripeCustomerId: "cus_123", stripePaymentMethodId: "pm_123" }],
      [{ stripeCustomerId: "cus_123", stripePaymentMethodId: "pm_newer" }],
    ]);
  });

  it("clears the saved card when the customer's default was removed", async () => {
    const { clearCustomerPaymentMethod, deliver, updateCustomerPaymentMethod } =
      createPayments({
        savedCard: null,
        event: {
          type: "customer.updated",
          data: {
            object: {
              id: "cus_123",
              invoice_settings: { default_payment_method: null },
            },
          },
        },
      });

    await deliver();

    expect(clearCustomerPaymentMethod).toHaveBeenCalledWith("cus_123");
    expect(updateCustomerPaymentMethod).not.toHaveBeenCalled();
  });

  it("fails a pending charge whose invoice payment failed later", async () => {
    const { deliver, fail } = createPayments({
      event: {
        type: "invoice.payment_failed",
        data: {
          object: {
            id: "in_123",
            metadata: { kind: "top_up_charge", top_up_charge_id: chargeId },
          },
        },
      },
    });

    await deliver();

    expect(fail).toHaveBeenCalledWith({
      chargeId,
      failure: "The payment failed.",
    });
  });

  it("credits a paid top-up charge invoice", async () => {
    const { deliver, succeed } = createPayments({ event: invoiceEvent() });

    await deliver();

    expect(succeed).toHaveBeenCalledWith({
      chargeId,
      stripeInvoiceId: "in_123",
      amount: 50_000_000_000n,
    });
  });

  it("ignores invoices that Checkout top-ups create", async () => {
    const { deliver, succeed } = createPayments({
      event: invoiceEvent({}, "balance_topup"),
    });

    await deliver();

    expect(succeed).not.toHaveBeenCalled();
  });

  it("rejects a top-up charge invoice in another currency", async () => {
    const { deliver, succeed } = createPayments({
      event: invoiceEvent({ currency: "eur" }),
    });

    await expect(deliver()).rejects.toMatchObject({ code: "invalid_webhook" });
    expect(succeed).not.toHaveBeenCalled();
  });
});
