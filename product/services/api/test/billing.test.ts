import { ControlServiceError } from "@gradiated/control";
import { describe, expect, it, vi } from "vitest";

import { BillingPaymentsError } from "../src/billing/payments.js";
import {
  authenticated,
  balanceTransactionRecord,
  billingAccountRecord,
  controlServiceProblems,
  createTestApp,
  expectProblem,
  failWith,
  organizationId,
  postJson,
  user,
  validationProblem,
  type TestApp,
} from "./support.js";

const billingPath = `/api/v1/organizations/${organizationId}/billing`;
const balanceTransactionsPath = `/api/v1/organizations/${organizationId}/balance-transactions`;
const topUpsPath = `/api/v1/organizations/${organizationId}/billing/top-ups`;
const paymentMethodSessionsPath = `/api/v1/organizations/${organizationId}/billing/payment-method-sessions`;
const webhookPath = "/api/webhooks/stripe";

const patchJson = (app: TestApp, path: string, body: unknown) =>
  app.request(path, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

const autoTopUp = {
  enabled: true,
  threshold: "10000000000",
  amount: "50000000000",
};

const billingProviderUnavailable = {
  status: 503,
  type: "billing-provider-unavailable",
} as const;

const billingReadEndpoints = [
  { name: "billing account", path: billingPath },
  { name: "balance transactions", path: balanceTransactionsPath },
];

const sendWebhook = (app: TestApp, headers: Record<string, string>) =>
  app.request(webhookPath, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...headers },
    body: "{}",
  });

describe("billing routes", () => {
  it("returns balances as precise decimal strings", async () => {
    const app = createTestApp({
      auth: authenticated,
      services: {
        catalogBilling: {
          getBillingAccount: async () => billingAccountRecord,
          listBalanceTransactions: async () => ({
            data: [balanceTransactionRecord],
            nextCursor: null,
          }),
        },
      },
    });

    const account = await app.request(billingPath);
    const transactions = await app.request(balanceTransactionsPath);

    expect(account.status).toBe(200);
    await expect(account.json()).resolves.toMatchObject({
      balance: "100000000000",
      mode: "prepaid",
    });
    expect(transactions.status).toBe(200);
    await expect(transactions.json()).resolves.toMatchObject({
      data: [
        {
          amount: "100000000000",
          balance_after: "100000000000",
          stripe_id: null,
        },
      ],
    });
  });

  it("passes pagination parameters and returns the next cursor", async () => {
    const listBalanceTransactions = vi.fn().mockResolvedValue({
      data: [balanceTransactionRecord],
      nextCursor: balanceTransactionRecord.id,
    });
    const app = createTestApp({
      auth: authenticated,
      services: { catalogBilling: { listBalanceTransactions } },
    });

    const response = await app.request(
      `${balanceTransactionsPath}?limit=10&cursor=${balanceTransactionRecord.id}`,
    );

    expect(response.status).toBe(200);
    expect(listBalanceTransactions).toHaveBeenCalledWith(
      user.id,
      organizationId,
      { limit: 10, cursor: balanceTransactionRecord.id },
    );
    expect(await response.json()).toMatchObject({
      next_cursor: balanceTransactionRecord.id,
    });
  });

  it.each(["limit=0", "limit=101", "limit=1.5", "limit=abc", "cursor=invalid"])(
    "rejects invalid pagination: %s",
    async (query) => {
      const listBalanceTransactions = vi.fn();
      const app = createTestApp({
        auth: authenticated,
        services: { catalogBilling: { listBalanceTransactions } },
      });

      await expectProblem(
        await app.request(`${balanceTransactionsPath}?${query}`),
        validationProblem,
      );
      expect(listBalanceTransactions).not.toHaveBeenCalled();
    },
  );

  it("creates a top-up Checkout Session for the selected organization", async () => {
    const received: unknown[] = [];
    const app = createTestApp({
      auth: authenticated,
      services: {
        billingPayments: {
          createTopUp: async (input) => {
            received.push(input);

            return {
              status: "checkout",
              checkoutUrl: "https://checkout.stripe.com/c/pay/test",
            };
          },
        },
      },
    });

    const response = await postJson(app, topUpsPath, { amount: "50000000000" });

    expect(response.status).toBe(201);
    expect(received).toEqual([
      {
        userId: user.id,
        userEmail: user.email,
        organizationId,
        amount: 50_000_000_000n,
      },
    ]);
    await expect(response.json()).resolves.toEqual({
      status: "checkout",
      checkout_url: "https://checkout.stripe.com/c/pay/test",
    });
  });

  it("charges the saved card when asked to and reports it paid", async () => {
    const createTopUp = vi.fn(async () => ({
      status: "paid" as const,
      checkoutUrl: null,
    }));
    const app = createTestApp({
      auth: authenticated,
      services: { billingPayments: { createTopUp } },
    });

    const response = await postJson(app, topUpsPath, {
      amount: "50000000000",
      method: "card",
    });

    expect(response.status).toBe(201);
    expect(createTopUp).toHaveBeenCalledWith(
      expect.objectContaining({ method: "card" }),
    );
    await expect(response.json()).resolves.toEqual({
      status: "paid",
      checkout_url: null,
    });
  });

  it("returns the saved card and auto top-up settings", async () => {
    const app = createTestApp({
      auth: authenticated,
      services: {
        billingPayments: {
          describeCard: async (paymentMethodId) =>
            paymentMethodId === "pm_123"
              ? { brand: "visa", last4: "4242", expMonth: 8, expYear: 2028 }
              : null,
        },
        catalogBilling: {
          getBillingAccount: async () => ({
            ...billingAccountRecord,
            stripePaymentMethodId: "pm_123",
            autoTopUpEnabled: true,
            autoTopUpThreshold: 10_000_000_000n,
            autoTopUpAmount: 50_000_000_000n,
          }),
        },
      },
    });

    const response = await app.request(billingPath);

    await expect(response.json()).resolves.toMatchObject({
      payment_method: {
        brand: "visa",
        last4: "4242",
        exp_month: 8,
        exp_year: 2028,
      },
      auto_top_up: { ...autoTopUp, failure: null },
    });
  });

  it("shows a saved card without details when Stripe is unreachable", async () => {
    const app = createTestApp({
      auth: authenticated,
      services: {
        billingPayments: { describeCard: async () => null },
        catalogBilling: {
          getBillingAccount: async () => ({
            ...billingAccountRecord,
            stripeCustomerId: "cus_123",
            stripePaymentMethodId: "pm_123",
          }),
        },
      },
    });

    const response = await app.request(billingPath);

    await expect(response.json()).resolves.toMatchObject({
      billing_portal: true,
      payment_method: {
        brand: null,
        last4: null,
        exp_month: null,
        exp_year: null,
      },
    });
  });

  it("reports the last auto top-up failure while auto top-up is off", async () => {
    const topUpStatus = vi.fn(async () => ({
      pending: true,
      autoTopUpFailure: "Your card was declined.",
    }));
    const app = createTestApp({
      auth: authenticated,
      services: {
        catalogBilling: {
          getBillingAccount: async () => billingAccountRecord,
          topUpStatus,
        },
      },
    });

    const response = await app.request(billingPath);

    await expect(response.json()).resolves.toMatchObject({
      auto_top_up: { failure: "Your card was declined." },
      top_up_pending: true,
    });
    expect(topUpStatus).toHaveBeenCalledWith(organizationId);
  });

  it("updates auto top-up settings", async () => {
    const updateAutoTopUp = vi.fn(async () => ({
      ...billingAccountRecord,
      autoTopUpEnabled: true,
      autoTopUpThreshold: 10_000_000_000n,
      autoTopUpAmount: 50_000_000_000n,
    }));
    const app = createTestApp({
      auth: authenticated,
      services: { catalogBilling: { updateAutoTopUp } },
    });

    const response = await patchJson(app, billingPath, {
      auto_top_up: autoTopUp,
    });

    expect(response.status).toBe(200);
    expect(updateAutoTopUp).toHaveBeenCalledWith(
      user.id,
      organizationId,
      autoTopUp,
    );
    await expect(response.json()).resolves.toMatchObject({
      auto_top_up: autoTopUp,
    });
  });

  it.each([
    { ...autoTopUp, amount: "4990000000" },
    { ...autoTopUp, threshold: "-1" },
    { ...autoTopUp, threshold: "10000000001" },
    {},
  ])("rejects invalid auto top-up settings %o", async (settings) => {
    const updateAutoTopUp = vi.fn();
    const app = createTestApp({
      auth: authenticated,
      services: { catalogBilling: { updateAutoTopUp } },
    });

    const response = await patchJson(app, billingPath, {
      auto_top_up: settings,
    });

    await expectProblem(response, validationProblem);
    expect(updateAutoTopUp).not.toHaveBeenCalled();
  });

  it("answers auto top-up without a saved card with 409", async () => {
    const app = createTestApp({
      auth: authenticated,
      services: {
        catalogBilling: {
          updateAutoTopUp: failWith(
            new ControlServiceError("conflict", "Save a card first."),
          ),
        },
      },
    });

    const response = await patchJson(app, billingPath, {
      auto_top_up: autoTopUp,
    });

    expect(response.status).toBe(409);
  });

  it("creates a payment method session", async () => {
    const createPaymentMethodSession = vi.fn(async () => ({
      url: "https://checkout.stripe.com/c/pay/setup",
    }));
    const app = createTestApp({
      auth: authenticated,
      services: { billingPayments: { createPaymentMethodSession } },
    });

    const response = await app.request(paymentMethodSessionsPath, {
      method: "POST",
    });

    expect(response.status).toBe(201);
    expect(createPaymentMethodSession).toHaveBeenCalledWith({
      userId: user.id,
      userEmail: user.email,
      organizationId,
    });
    await expect(response.json()).resolves.toEqual({
      url: "https://checkout.stripe.com/c/pay/setup",
    });
  });

  it("updates one auto top-up setting", async () => {
    const updateAutoTopUp = vi.fn(async () => billingAccountRecord);
    const app = createTestApp({
      auth: authenticated,
      services: { catalogBilling: { updateAutoTopUp } },
    });

    const response = await patchJson(app, billingPath, {
      auto_top_up: { enabled: false },
    });

    expect(response.status).toBe(200);
    expect(updateAutoTopUp).toHaveBeenCalledWith(user.id, organizationId, {
      enabled: false,
    });
  });

  it("passes the unmodified signed body to the Stripe webhook handler", async () => {
    const payload = '{\n  "id": "evt_test_123"\n}';
    const received: unknown[] = [];
    const app = createTestApp({
      services: {
        billingPayments: {
          handleWebhook: async (input) => {
            received.push(input);
          },
        },
      },
    });

    const response = await app.request(webhookPath, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Stripe-Signature": "signed",
      },
      body: payload,
    });

    expect(response.status).toBe(200);
    expect(received).toEqual([{ payload, signature: "signed" }]);
    await expect(response.json()).resolves.toEqual({ received: true });
  });

  it.each(
    billingReadEndpoints.flatMap((endpoint) =>
      controlServiceProblems.map((problem) => ({ ...endpoint, problem })),
    ),
  )(
    "maps $problem.code on $name to $problem.status",
    async ({ path, problem }) => {
      const error = new ControlServiceError(problem.code, "Rejected.");
      const app = createTestApp({
        auth: authenticated,
        services: {
          catalogBilling: {
            getBillingAccount: failWith(error),
            listBalanceTransactions: failWith(error),
          },
        },
      });

      await expectProblem(await app.request(path), problem);
    },
  );

  it.each([
    {
      code: "not_prepaid",
      problem: { status: 409, type: "not-prepaid" },
    },
    {
      code: "payment_failed",
      problem: { status: 402, type: "payment-failed" },
    },
    { code: "provider_error", problem: billingProviderUnavailable },
    { code: "unavailable", problem: billingProviderUnavailable },
  ] as const)(
    "maps top-up $code to $problem.status",
    async ({ code, problem }) => {
      const app = createTestApp({
        auth: authenticated,
        services: {
          billingPayments: {
            createTopUp: failWith(new BillingPaymentsError(code, "Rejected.")),
          },
        },
      });

      const response = await postJson(app, topUpsPath, {
        amount: "50000000000",
      });

      await expectProblem(response, { ...problem, code });
    },
  );

  it.each(controlServiceProblems)(
    "maps top-up account $code to $status",
    async (problem) => {
      const app = createTestApp({
        auth: authenticated,
        services: {
          billingPayments: {
            createTopUp: failWith(
              new ControlServiceError(problem.code, "Rejected."),
            ),
          },
        },
      });

      const response = await postJson(app, topUpsPath, {
        amount: "50000000000",
      });

      await expectProblem(response, problem);
    },
  );

  it.each([
    { name: "below $5", amount: "4990000000" },
    { name: "above $10,000", amount: "10000010000000" },
    { name: "with sub-cent precision", amount: "5000000001" },
  ])("rejects a top-up $name", async ({ amount }) => {
    const received: unknown[] = [];
    const app = createTestApp({
      auth: authenticated,
      services: {
        billingPayments: {
          createTopUp: async (input) => {
            received.push(input);

            return {
              status: "checkout",
              checkoutUrl: "https://checkout.stripe.com/c/pay/test",
            };
          },
        },
      },
    });

    const response = await postJson(app, topUpsPath, { amount });

    await expectProblem(response, validationProblem);
    expect(received).toEqual([]);
  });

  it.each([
    {
      code: "invalid_webhook",
      problem: { status: 400, type: "invalid-stripe-webhook" },
    },
    { code: "unavailable", problem: billingProviderUnavailable },
  ] as const)(
    "maps webhook $code to $problem.status",
    async ({ code, problem }) => {
      const app = createTestApp({
        services: {
          billingPayments: {
            handleWebhook: failWith(
              new BillingPaymentsError(code, "Rejected."),
            ),
          },
        },
      });

      const response = await sendWebhook(app, { "Stripe-Signature": "signed" });

      await expectProblem(response, { ...problem, code });
    },
  );

  it("answers a failed credit with 503 so Stripe retries the event", async () => {
    const app = createTestApp({
      services: {
        billingPayments: {
          handleWebhook: failWith(
            new ControlServiceError("unavailable", "Ledger unavailable."),
          ),
        },
      },
    });

    const response = await sendWebhook(app, { "Stripe-Signature": "signed" });

    await expectProblem(response, {
      status: 503,
      code: "unavailable",
      type: "unavailable",
    });
  });

  it("rejects a webhook without a Stripe signature", async () => {
    const response = await sendWebhook(createTestApp(), {});

    await expectProblem(response, validationProblem);
  });
});
