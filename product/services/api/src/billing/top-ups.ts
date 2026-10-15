import { CreateTopUpCheckoutSchema } from "@gradiated/contracts";
import type { CatalogBillingService } from "@gradiated/control";
import { z } from "@hono/zod-openapi";

import { serviceLog } from "../logging.js";
import type { StripeGateway } from "./stripe-gateway.js";

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

const isTopUpAmount = (amount: bigint): boolean =>
  CreateTopUpCheckoutSchema.shape.amount.safeParse(amount.toString()).success;

const TopUpEventSchema = z.object({
  type: StripeCheckoutEventSchema.shape.type,
  data: z.object({
    object: z.object({
      metadata: z.object({ kind: TopUpMetadataSchema.shape.kind }),
    }),
  }),
});

type TopUpRejection =
  "schema" | "metadata_mismatch" | "currency" | "amount_out_of_range";

const topUpRejection = (
  reason: TopUpRejection,
  cause?: unknown,
): BillingPaymentsError => {
  serviceLog(
    "error",
    `stripe_topup_rejected_${reason}`,
    cause === undefined ? {} : { error: cause },
  );

  return new BillingPaymentsError(
    "invalid_webhook",
    "The Stripe Checkout event does not describe a valid top-up.",
    cause,
  );
};

export const createBillingPaymentsService = ({
  gateway,
  accounts,
  productUrl,
}: {
  gateway: StripeGateway;
  accounts: Pick<
    CatalogBillingService,
    "getManagedBillingAccount" | "applyBalanceTransaction"
  >;
  productUrl: string;
}): BillingPaymentsService => {
  const baseProductUrl = productUrl.replace(/\/$/, "");

  return {
    createTopUpCheckout: async (input) => {
      if (!isTopUpAmount(input.amount)) {
        throw new RangeError(
          "Top-up amounts must be between $5 and $10,000 in whole cents.",
        );
      }

      const account = await accounts.getManagedBillingAccount(
        input.userId,
        input.organizationId,
      );
      if (account.mode !== "prepaid") {
        throw new BillingPaymentsError(
          "not_prepaid",
          "Checkout top-ups are only available for prepaid organizations.",
        );
      }

      let checkoutUrl: string | null;
      try {
        ({ url: checkoutUrl } = await gateway.createCheckoutSession({
          amountCents: Number(input.amount / NanoUsdPerCent),
          organizationId: input.organizationId,
          userId: input.userId,
          customerId: account.stripeCustomerId,
          customerEmail: input.userEmail,
          successUrl: `${baseProductUrl}/billing?topup=success&session_id={CHECKOUT_SESSION_ID}`,
          cancelUrl: `${baseProductUrl}/billing?topup=cancelled`,
        }));
      } catch (error) {
        throw new BillingPaymentsError(
          "provider_error",
          "Stripe could not start Checkout.",
          error,
        );
      }

      if (!checkoutUrl) {
        throw new BillingPaymentsError(
          "provider_error",
          "Stripe did not return a Checkout URL.",
        );
      }

      return { checkoutUrl };
    },

    handleWebhook: async ({ payload, signature }) => {
      let event: unknown;
      try {
        event = gateway.constructWebhookEvent(payload, signature);
      } catch (error) {
        serviceLog("warn", "stripe_webhook_signature_invalid", { error });

        throw new BillingPaymentsError(
          "invalid_webhook",
          "The Stripe webhook signature is invalid.",
          error,
        );
      }

      if (!TopUpEventSchema.safeParse(event).success) return;

      const parsed = StripeCheckoutEventSchema.safeParse(event);
      if (!parsed.success) throw topUpRejection("schema", parsed.error);

      const session = parsed.data.data.object;
      if (session.payment_status !== "paid") return;

      const metadata = TopUpMetadataSchema.safeParse(session.metadata);
      if (
        !metadata.success ||
        session.client_reference_id !== metadata.data.organization_id
      ) {
        throw topUpRejection("metadata_mismatch", metadata.error);
      }

      if (session.currency !== "usd") throw topUpRejection("currency");

      const amount =
        session.amount_total === null
          ? null
          : BigInt(session.amount_total) * NanoUsdPerCent;
      if (amount === null || !isTopUpAmount(amount)) {
        throw topUpRejection("amount_out_of_range");
      }

      const customerId =
        typeof session.customer === "string"
          ? session.customer
          : (session.customer?.id ?? null);

      await accounts.applyBalanceTransaction({
        organizationId: metadata.data.organization_id,
        type: "topup",
        amount,
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
