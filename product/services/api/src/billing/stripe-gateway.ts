import Stripe from "stripe";

export interface CheckoutSessionInput {
  amountCents: number;
  organizationId: string;
  userId: string;
  customerId: string;
  // The saved card when Checkout opened; the webhook replaces only that one.
  replacesPaymentMethodId: string | null;
  // A retried request with the same key gets the same session from Stripe.
  requestKey?: string;
  successUrl: string;
  cancelUrl: string;
}

export type SavedCard = {
  customerId: string;
  paymentMethodId: string;
  brand: string;
  last4: string;
  expMonth: number;
  expYear: number;
};

export type CardSetupInput = {
  organizationId: string;
  userId: string;
  customerId: string;
  // The saved card when setup began; a later save does not replace a newer one.
  replacesPaymentMethodId: string | null;
};

export interface StripeGateway {
  createCheckoutSession(
    input: CheckoutSessionInput,
  ): Promise<{ url: string | null }>;
  createCustomer(input: {
    organizationId: string;
    email: string;
  }): Promise<{ customerId: string }>;
  retrieveDefaultCard(customerId: string): Promise<SavedCard | null>;
  createCardSetup(input: CardSetupInput): Promise<{ clientSecret: string }>;
  retrieveCardSetup(setupIntentId: string): Promise<{
    organizationId: string | null;
    replacesPaymentMethodId: string | null;
    card: SavedCard | null;
  }>;
  retrievePaymentCard(paymentIntentId: string): Promise<SavedCard | null>;
  retrieveCard(paymentMethodId: string): Promise<SavedCard | null>;
  setDefaultPaymentMethod(
    customerId: string,
    paymentMethodId: string,
  ): Promise<void>;
  createBillingPortalSession(input: {
    customerId: string;
    returnUrl: string;
  }): Promise<{ url: string }>;
  constructWebhookEvent(payload: string, signature: string): unknown;
}

export const stripeId = (
  value: string | { id: string } | null,
): string | null => (typeof value === "string" ? value : (value?.id ?? null));

const savedCard = (method: Stripe.PaymentMethod): SavedCard | null => {
  const customerId = stripeId(method.customer);
  if (!customerId || !method.card) return null;

  return {
    customerId,
    paymentMethodId: method.id,
    brand: method.card.brand,
    last4: method.card.last4,
    expMonth: method.card.exp_month,
    expYear: method.card.exp_year,
  };
};

export const createStripeGateway = (input: {
  stripe: Stripe;
  webhookSecret: string;
}): StripeGateway => {
  const { stripe } = input;

  return {
    createCheckoutSession: async (session) => {
      const metadata = {
        kind: "balance_topup",
        organization_id: session.organizationId,
        user_id: session.userId,
        replaces_payment_method: session.replacesPaymentMethodId ?? "",
      };
      const created = await stripe.checkout.sessions.create(
        {
          customer: session.customerId,
          mode: "payment",
          // Only a card can be saved and charged later for top-ups and auto top-up.
          payment_method_types: ["card"],
          client_reference_id: session.organizationId,
          metadata,
          // Keep the card on the customer so later top-ups and auto top-up can charge it.
          payment_intent_data: { metadata, setup_future_usage: "off_session" },
          invoice_creation: {
            enabled: true,
            invoice_data: { description: "Inference credits", metadata },
          },
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
        },
        session.requestKey
          ? {
              idempotencyKey: `checkout:${session.organizationId}:${session.requestKey}`,
            }
          : {},
      );

      return { url: created.url };
    },
    // One key per organization, so concurrent first payments share a customer.
    // The key's parameters must match across callers, so the caller's email is
    // added afterwards, only when the customer has none.
    createCustomer: async ({ organizationId, email }) => {
      const customer = await stripe.customers.create(
        { metadata: { organization_id: organizationId } },
        { idempotencyKey: `customer:${organizationId}` },
      );
      if (!customer.email) {
        await stripe.customers.update(customer.id, { email });
      }

      return { customerId: customer.id };
    },
    retrieveDefaultCard: async (customerId) => {
      const customer = await stripe.customers.retrieve(customerId, {
        expand: ["invoice_settings.default_payment_method"],
      });
      if (customer.deleted) return null;

      const method = customer.invoice_settings.default_payment_method;

      return method && typeof method !== "string" ? savedCard(method) : null;
    },
    createCardSetup: async (input) => {
      const metadata = {
        kind: "card_setup",
        organization_id: input.organizationId,
        user_id: input.userId,
        replaces_payment_method: input.replacesPaymentMethodId ?? "",
      };
      const intent = await stripe.setupIntents.create({
        customer: input.customerId,
        payment_method_types: ["card"],
        usage: "off_session",
        metadata,
      });
      if (!intent.client_secret) {
        throw new Error(
          "Stripe returned a SetupIntent without a client secret.",
        );
      }

      return { clientSecret: intent.client_secret };
    },
    retrieveCardSetup: async (setupIntentId) => {
      const intent = await stripe.setupIntents.retrieve(setupIntentId, {
        expand: ["payment_method"],
      });
      const method = intent.payment_method;

      return {
        organizationId: intent.metadata?.organization_id ?? null,
        replacesPaymentMethodId:
          intent.metadata?.replaces_payment_method || null,
        card:
          intent.status === "succeeded" && method && typeof method !== "string"
            ? savedCard(method)
            : null,
      };
    },
    retrievePaymentCard: async (paymentIntentId) => {
      const intent = await stripe.paymentIntents.retrieve(paymentIntentId, {
        expand: ["payment_method"],
      });
      const method = intent.payment_method;
      if (
        intent.status !== "succeeded" ||
        !method ||
        typeof method === "string"
      )
        return null;

      return savedCard(method);
    },
    retrieveCard: async (paymentMethodId) =>
      savedCard(await stripe.paymentMethods.retrieve(paymentMethodId)),
    setDefaultPaymentMethod: async (customerId, paymentMethodId) => {
      await stripe.customers.update(customerId, {
        invoice_settings: { default_payment_method: paymentMethodId },
      });
    },
    createBillingPortalSession: async ({ customerId, returnUrl }) => {
      const session = await stripe.billingPortal.sessions.create({
        customer: customerId,
        return_url: returnUrl,
      });

      return { url: session.url };
    },
    constructWebhookEvent: (payload, signature) =>
      stripe.webhooks.constructEvent(payload, signature, input.webhookSecret),
  };
};
