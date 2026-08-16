import { z } from "@hono/zod-openapi";
import type { CatalogBillingService } from "@gradiated/control";
import Stripe from "stripe";

const NanoUsdPerCent = 10_000_000n;

const StripeCheckoutEventSchema = z.object({
  type: z.enum([
    "checkout.session.completed",
    "checkout.session.async_payment_succeeded",
  ]),
  data: z.object({
    object: z.object({
      id: z.string().min(1),
      mode: z.literal("payment"),
      payment_status: z.enum(["paid", "unpaid", "no_payment_required"]),
      currency: z.string().nullable(),
      amount_total: z.number().int().nonnegative().nullable(),
      customer: z.union([z.string(), z.object({ id: z.string() })]).nullable(),
      client_reference_id: z.string().nullable(),
      metadata: z.record(z.string(), z.string()).nullable(),
    }),
  }),
});

const TopUpMetadataSchema = z.object({
  kind: z.literal("balance_topup"),
  organization_id: z.uuid(),
  user_id: z.uuid(),
});

interface CheckoutSessionInput {
  amountCents: number;
  organizationId: string;
  userId: string;
  customerId: string | null;
  customerEmail: string;
  successUrl: string;
  cancelUrl: string;
}

interface CheckoutSessionResult {
  id: string;
  url: string | null;
}

export interface StripeGateway {
  createCheckoutSession(
    input: CheckoutSessionInput,
  ): Promise<CheckoutSessionResult>;
  constructWebhookEvent(payload: string, signature: string): unknown;
}

export interface BillingPaymentsService {
  createTopUpCheckout(input: {
    userId: string;
    userEmail: string;
    organizationId: string;
    amount: bigint;
  }): Promise<{ checkoutUrl: string }>;
  handleWebhook(input: { payload: string; signature: string }): Promise<void>;
}

export class BillingPaymentsError extends Error {
  constructor(
    readonly code:
      "invalid_webhook" | "not_prepaid" | "provider_error" | "unavailable",
    message: string,
    override readonly cause?: unknown,
  ) {
    super(message);
    this.name = "BillingPaymentsError";
  }
}

export const createStripeGateway = (input: {
  secretKey: string;
  webhookSecret: string;
}): StripeGateway => {
  const stripe = new Stripe(input.secretKey, {
    apiVersion: "2026-07-29.dahlia",
  });

  return {
    createCheckoutSession: async (session) => {
      const metadata = {
        kind: "balance_topup",
        organization_id: session.organizationId,
        user_id: session.userId,
      };
      const customer = session.customerId
        ? { customer: session.customerId }
        : {
            customer_creation: "always" as const,
            customer_email: session.customerEmail,
          };
      const created = await stripe.checkout.sessions.create({
        ...customer,
        mode: "payment",
        client_reference_id: session.organizationId,
        metadata,
        payment_intent_data: { metadata },
        line_items: [
          {
            quantity: 1,
            price_data: {
              currency: "usd",
              unit_amount: session.amountCents,
              product_data: { name: "Inference credits" },
            },
          },
        ],
        success_url: session.successUrl,
        cancel_url: session.cancelUrl,
      });
      return { id: created.id, url: created.url };
    },
    constructWebhookEvent: (payload, signature) =>
      stripe.webhooks.constructEvent(payload, signature, input.webhookSecret),
  };
};

export const createBillingPaymentsService = (
  gateway: StripeGateway,
  catalogBilling: CatalogBillingService,
  productUrl: string,
): BillingPaymentsService => {
  const baseProductUrl = productUrl.replace(/\/$/, "");
  return {
    createTopUpCheckout: async (input) => {
      const account = await catalogBilling.getBillingAccount(
        input.userId,
        input.organizationId,
      );
      if (account.mode !== "prepaid") {
        throw new BillingPaymentsError(
          "not_prepaid",
          "Checkout top-ups are only available for prepaid organizations.",
        );
      }

      let session: CheckoutSessionResult;
      try {
        session = await gateway.createCheckoutSession({
          amountCents: Number(input.amount / NanoUsdPerCent),
          organizationId: input.organizationId,
          userId: input.userId,
          customerId: account.stripeCustomerId,
          customerEmail: input.userEmail,
          successUrl: `${baseProductUrl}/billing?topup=success&session_id={CHECKOUT_SESSION_ID}`,
          cancelUrl: `${baseProductUrl}/billing?topup=cancelled`,
        });
      } catch (error) {
        throw new BillingPaymentsError(
          "provider_error",
          "Stripe could not start Checkout.",
          error,
        );
      }
      if (!session.url) {
        throw new BillingPaymentsError(
          "provider_error",
          "Stripe did not return a Checkout URL.",
        );
      }
      return { checkoutUrl: session.url };
    },

    handleWebhook: async ({ payload, signature }) => {
      let event: unknown;
      try {
        event = gateway.constructWebhookEvent(payload, signature);
      } catch (error) {
        throw new BillingPaymentsError(
          "invalid_webhook",
          "The Stripe webhook signature is invalid.",
          error,
        );
      }

      if (
        !event ||
        typeof event !== "object" ||
        !("type" in event) ||
        ![
          "checkout.session.completed",
          "checkout.session.async_payment_succeeded",
        ].includes(String(event.type))
      ) {
        return;
      }

      const parsed = StripeCheckoutEventSchema.safeParse(event);
      if (!parsed.success) {
        throw new BillingPaymentsError(
          "invalid_webhook",
          "The Stripe Checkout event is incomplete.",
          parsed.error,
        );
      }
      const session = parsed.data.data.object;
      if (session.payment_status !== "paid") return;

      const metadata = TopUpMetadataSchema.safeParse(session.metadata);
      if (
        !metadata.success ||
        session.client_reference_id !== metadata.data.organization_id ||
        session.currency !== "usd" ||
        session.amount_total === null ||
        session.amount_total < 500 ||
        session.amount_total > 1_000_000
      ) {
        throw new BillingPaymentsError(
          "invalid_webhook",
          "The Stripe Checkout event does not describe a valid top-up.",
        );
      }

      const customerId =
        typeof session.customer === "string"
          ? session.customer
          : (session.customer?.id ?? null);
      await catalogBilling.applyBalanceTransaction({
        organizationId: metadata.data.organization_id,
        type: "topup",
        amount: BigInt(session.amount_total) * NanoUsdPerCent,
        sourceType: "stripe_checkout_session",
        sourceId: session.id,
        createdBy: metadata.data.user_id,
        stripeCustomerId: customerId,
      });
    },
  };
};

export const unavailableBillingPaymentsService =
  (): BillingPaymentsService => ({
    createTopUpCheckout: async () => {
      throw new BillingPaymentsError(
        "unavailable",
        "Stripe Checkout is not configured.",
      );
    },
    handleWebhook: async () => {
      throw new BillingPaymentsError(
        "unavailable",
        "Stripe webhooks are not configured.",
      );
    },
  });
