import { describe, expect, it, vi } from "vitest";

import type { CatalogBillingService } from "@gradiated/control";

import {
  createBillingPaymentsService,
  type StripeGateway,
} from "../src/billing/stripe.js";
import { now, organizationId, user } from "./support.js";

const billingAccount = {
  organizationId,
  mode: "prepaid" as const,
  stripeCustomerId: null,
  balance: 0n,
  createdAt: now,
  updatedAt: now,
};

const catalogBillingService = () => {
  const applyBalanceTransaction = vi.fn(async (input) => ({
    id: "0198ae70-68b0-7644-812d-c4bf16a926e3",
    organizationId: input.organizationId,
    type: input.type,
    amount: input.amount,
    balanceAfter: input.amount,
    sourceType: input.sourceType,
    sourceId: input.sourceId,
    periodStart: null,
    periodEnd: null,
    generationCount: null,
    createdBy: input.createdBy,
    createdAt: now,
  }));
  const service: CatalogBillingService = {
    listModels: async () => [],
    getBillingAccount: async () => billingAccount,
    listBalanceTransactions: async () => [],
    upsertModel: async () => {
      throw new Error("not used");
    },
    upsertModelDeployment: async () => {
      throw new Error("not used");
    },
    initializeCurrentAccount: async () => undefined,
    projectCurrentAccount: async () => undefined,
    applyBalanceTransaction,
  };
  return { applyBalanceTransaction, service };
};

const checkoutEvent = (paymentStatus: "paid" | "unpaid") => ({
  type: "checkout.session.completed",
  data: {
    object: {
      id: "cs_test_123",
      mode: "payment",
      payment_status: paymentStatus,
      currency: "usd",
      amount_total: 5_000,
      customer: "cus_123",
      client_reference_id: organizationId,
      metadata: {
        kind: "balance_topup",
        organization_id: organizationId,
        user_id: user.id,
      },
    },
  },
});

describe("Stripe billing payments", () => {
  it("creates a server-priced Checkout Session", async () => {
    const createCheckoutSession = vi.fn(async () => ({
      id: "cs_test_123",
      url: "https://checkout.stripe.com/c/pay/cs_test_123",
    }));
    const gateway: StripeGateway = {
      createCheckoutSession,
      constructWebhookEvent: () => ({ type: "unhandled" }),
    };
    const { service: catalogBilling } = catalogBillingService();
    const payments = createBillingPaymentsService(
      gateway,
      catalogBilling,
      "http://localhost:3000",
    );

    await expect(
      payments.createTopUpCheckout({
        userId: user.id,
        userEmail: user.email,
        organizationId,
        amount: 50_000_000_000n,
      }),
    ).resolves.toEqual({
      checkoutUrl: "https://checkout.stripe.com/c/pay/cs_test_123",
    });
    expect(createCheckoutSession).toHaveBeenCalledWith(
      expect.objectContaining({
        amountCents: 5_000,
        organizationId,
        customerEmail: user.email,
        successUrl:
          "http://localhost:3000/billing?topup=success&session_id={CHECKOUT_SESSION_ID}",
      }),
    );
  });

  it("credits a paid Checkout Session in nano-USD", async () => {
    const gateway: StripeGateway = {
      createCheckoutSession: async () => {
        throw new Error("not used");
      },
      constructWebhookEvent: () => checkoutEvent("paid"),
    };
    const { applyBalanceTransaction, service: catalogBilling } =
      catalogBillingService();
    const payments = createBillingPaymentsService(
      gateway,
      catalogBilling,
      "http://localhost:3000",
    );

    await payments.handleWebhook({ payload: "{}", signature: "signed" });

    expect(applyBalanceTransaction).toHaveBeenCalledWith({
      organizationId,
      type: "topup",
      amount: 50_000_000_000n,
      sourceType: "stripe_checkout_session",
      sourceId: "cs_test_123",
      createdBy: user.id,
      stripeCustomerId: "cus_123",
    });
  });

  it("does not credit an unpaid or unrelated event", async () => {
    const events = [checkoutEvent("unpaid"), { type: "customer.created" }];
    const gateway: StripeGateway = {
      createCheckoutSession: async () => {
        throw new Error("not used");
      },
      constructWebhookEvent: () => events.shift(),
    };
    const { applyBalanceTransaction, service: catalogBilling } =
      catalogBillingService();
    const payments = createBillingPaymentsService(
      gateway,
      catalogBilling,
      "http://localhost:3000",
    );

    await payments.handleWebhook({ payload: "{}", signature: "signed" });
    await payments.handleWebhook({ payload: "{}", signature: "signed" });

    expect(applyBalanceTransaction).not.toHaveBeenCalled();
  });

  it("rejects an invalid webhook signature", async () => {
    const gateway: StripeGateway = {
      createCheckoutSession: async () => {
        throw new Error("not used");
      },
      constructWebhookEvent: () => {
        throw new Error("bad signature");
      },
    };
    const { service: catalogBilling } = catalogBillingService();
    const payments = createBillingPaymentsService(
      gateway,
      catalogBilling,
      "http://localhost:3000",
    );

    await expect(
      payments.handleWebhook({ payload: "{}", signature: "bad" }),
    ).rejects.toMatchObject({ code: "invalid_webhook" });
  });
});
