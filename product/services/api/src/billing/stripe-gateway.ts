import Stripe from "stripe";

export interface CheckoutSessionInput {
  amountCents: number;
  organizationId: string;
  userId: string;
  customerId: string | null;
  customerEmail: string;
  successUrl: string;
  cancelUrl: string;
}

export interface StripeGateway {
  createCheckoutSession(
    input: CheckoutSessionInput,
  ): Promise<{ url: string | null }>;
  constructWebhookEvent(payload: string, signature: string): unknown;
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

      return { url: created.url };
    },
    constructWebhookEvent: (payload, signature) =>
      stripe.webhooks.constructEvent(payload, signature, input.webhookSecret),
  };
};
