import { describe, expect, it } from "vitest";

import type { CatalogBillingService } from "@gradiated/control";

import { createApp } from "../src/app.js";
import { authenticated, now, organizationId, user } from "./support.js";

const modelProperties = {
  schema_version: 1,
  description: "Exact Kimi K3 inference.",
  released_at: null,
  hugging_face_id: "moonshotai/Kimi-K3",
  quantization: null,
  tokenizer: "Kimi",
  input_modalities: [{ type: "text" as const }],
  output_modalities: [{ type: "text" as const }],
  pricing: [
    { unit: "input_token" as const, cost: 2_800 },
    { unit: "output_token" as const, cost: 14_000 },
  ],
  capacity: [
    { metric: "context_tokens" as const, value: 262_144 },
    { metric: "max_output_tokens" as const, value: 32_768 },
  ],
  passthrough_parameters: { stream: { type: "boolean" as const } },
  deprecation_at: null,
  is_free: false,
  discount_to_user: 0,
  openrouter: null,
};

const catalogBillingService = (): CatalogBillingService => ({
  listModels: async () => [
    {
      id: "moonshotai/kimi-k3",
      name: "Kimi K3",
      status: "available",
      properties: modelProperties,
      createdAt: now,
      updatedAt: now,
    },
  ],
  getBillingAccount: async (_userId, receivedOrganizationId) => ({
    organizationId: receivedOrganizationId,
    mode: "prepaid",
    stripeCustomerId: null,
    balance: 100_000_000_000n,
    createdAt: now,
    updatedAt: now,
  }),
  listBalanceTransactions: async (_userId, receivedOrganizationId) => [
    {
      id: "0198ae70-68b0-7644-812d-c4bf16a926e3",
      organizationId: receivedOrganizationId,
      type: "credit",
      amount: 100_000_000_000n,
      balanceAfter: 100_000_000_000n,
      sourceType: "operator",
      sourceId: "local-credit",
      periodStart: null,
      periodEnd: null,
      generationCount: null,
      createdBy: user.id,
      createdAt: now,
    },
  ],
  upsertModel: async () => {
    throw new Error("not used");
  },
  projectCurrentAccount: async () => undefined,
  applyBalanceTransaction: async () => {
    throw new Error("not used");
  },
});

describe("catalog and billing routes", () => {
  it("lists the advertised exact models", async () => {
    const app = createApp({
      auth: authenticated,
      services: { catalogBilling: catalogBillingService() },
    });
    const response = await app.request("/api/v1/models");

    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toMatchObject({
      data: [
        {
          id: "moonshotai/kimi-k3",
          status: "available",
          properties: { pricing: [{ cost: 2_800 }, { cost: 14_000 }] },
        },
      ],
    });
  });

  it("returns balances as precise decimal strings", async () => {
    const app = createApp({
      auth: authenticated,
      services: { catalogBilling: catalogBillingService() },
    });
    const account = await app.request(
      `/api/v1/organizations/${organizationId}/billing`,
    );
    const transactions = await app.request(
      `/api/v1/organizations/${organizationId}/balance-transactions`,
    );

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

  it("creates a top-up Checkout Session for the selected organization", async () => {
    const createTopUpCheckout = async (input: {
      organizationId: string;
      amount: bigint;
    }) => {
      expect(input).toMatchObject({
        organizationId,
        amount: 50_000_000_000n,
      });
      return { checkoutUrl: "https://checkout.stripe.com/c/pay/test" };
    };
    const app = createApp({
      auth: authenticated,
      services: {
        catalogBilling: catalogBillingService(),
        billingPayments: {
          createTopUpCheckout,
          handleWebhook: async () => undefined,
        },
      },
    });

    const response = await app.request(
      `/api/v1/organizations/${organizationId}/billing/top-ups`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ amount: "50000000000" }),
      },
    );

    expect(response.status).toBe(201);
    await expect(response.json()).resolves.toEqual({
      checkout_url: "https://checkout.stripe.com/c/pay/test",
    });
  });

  it("passes the unmodified signed body to the Stripe webhook handler", async () => {
    const payload = '{\n  "id": "evt_test_123"\n}';
    const handleWebhook = async (input: {
      payload: string;
      signature: string;
    }) => {
      expect(input).toEqual({ payload, signature: "signed" });
    };
    const app = createApp({
      services: {
        billingPayments: {
          createTopUpCheckout: async () => {
            throw new Error("not used");
          },
          handleWebhook,
        },
      },
    });

    const response = await app.request("/api/webhooks/stripe", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Stripe-Signature": "signed",
      },
      body: payload,
    });

    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({ received: true });
  });
});
