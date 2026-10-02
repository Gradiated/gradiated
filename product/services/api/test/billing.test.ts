import { ControlServiceError } from "@gradiated/control";
import { describe, expect, it, vi } from "vitest";

import { BillingPaymentsError } from "../src/billing/top-ups.js";
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
const webhookPath = "/api/webhooks/stripe";

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
      data: [{ amount: "100000000000", balance_after: "100000000000" }],
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
          createTopUpCheckout: async (input) => {
            received.push(input);

            return { checkoutUrl: "https://checkout.stripe.com/c/pay/test" };
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
      checkout_url: "https://checkout.stripe.com/c/pay/test",
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
    { code: "provider_error", problem: billingProviderUnavailable },
    { code: "unavailable", problem: billingProviderUnavailable },
  ] as const)(
    "maps top-up $code to $problem.status",
    async ({ code, problem }) => {
      const app = createTestApp({
        auth: authenticated,
        services: {
          billingPayments: {
            createTopUpCheckout: failWith(
              new BillingPaymentsError(code, "Rejected."),
            ),
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
            createTopUpCheckout: failWith(
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
          createTopUpCheckout: async (input) => {
            received.push(input);

            return { checkoutUrl: "https://checkout.stripe.com/c/pay/test" };
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
