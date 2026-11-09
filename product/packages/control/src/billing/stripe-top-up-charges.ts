import { centsToNanoUsd, nanoUsdToCents } from "@gradiated/contracts";
import Stripe from "stripe";

import type { TopUpChargeRecord, TopUpChargeStore } from "./top-up-charges.js";

// Stripe keeps idempotency keys for 24 hours; a retry after that could charge twice.
const PENDING_EXPIRY_MILLISECONDS = 23 * 60 * 60_000;

export type TopUpChargeOutcome =
  | { status: "succeeded"; stripeInvoiceId: string; amount: bigint }
  | { status: "processing"; stripeInvoiceId: string }
  | { status: "failed"; failure: string; code: string };

export interface TopUpCharger {
  charge(
    charge: TopUpChargeRecord,
    onInvoice: (stripeInvoiceId: string) => Promise<void>,
  ): Promise<TopUpChargeOutcome>;
  resolve(charge: TopUpChargeRecord): Promise<TopUpChargeOutcome>;
}

export const createStripeClient = (secretKey: string): Stripe =>
  new Stripe(secretKey, { apiVersion: "2026-07-29.dahlia" });

const description = (charge: TopUpChargeRecord) =>
  charge.reason === "auto_top_up"
    ? "Inference credits (auto top-up)"
    : "Inference credits";

const settledOutcome = (invoice: Stripe.Invoice): TopUpChargeOutcome | null => {
  if (invoice.status === "paid") {
    return {
      status: "succeeded",
      stripeInvoiceId: invoice.id,
      amount: centsToNanoUsd(invoice.amount_paid),
    };
  }

  if (invoice.status === "void" || invoice.status === "uncollectible") {
    return {
      status: "failed",
      failure: "The payment was cancelled.",
      code: `invoice_${invoice.status}`,
    };
  }

  return null;
};

// Card declines, authentication requests and a detached card will not succeed
// on retry. Anything else is left pending and retried with the same keys.
const isFinalStripeError = (
  error: unknown,
): error is Stripe.errors.StripeError =>
  error instanceof Stripe.errors.StripeCardError ||
  error instanceof Stripe.errors.StripeInvalidRequestError;

export const createStripeTopUpCharger = (stripe: Stripe): TopUpCharger => {
  // Takes the invoice when the caller already has it, saving a retrieve.
  const discard = async (target: string | Stripe.Invoice | null) => {
    if (!target) return;

    const invoice =
      typeof target === "string"
        ? await stripe.invoices.retrieve(target)
        : target;
    if (invoice.status === "open")
      await stripe.invoices.voidInvoice(invoice.id);
    if (invoice.status === "draft") await stripe.invoices.del(invoice.id);
  };

  return {
    async charge(charge, onInvoice) {
      const key = (step: string) => ({
        idempotencyKey: `top-up-charge:${charge.id}:${step}`,
      });
      let invoiceId = charge.stripeInvoiceId;

      try {
        let invoice = invoiceId
          ? await stripe.invoices.retrieve(invoiceId)
          : await stripe.invoices.create(
              {
                customer: charge.stripeCustomerId,
                // Without this Stripe uses the customer's default currency,
                // which may not be USD, and rejects the USD line item.
                currency: "usd",
                collection_method: "charge_automatically",
                auto_advance: false,
                pending_invoice_items_behavior: "exclude",
                description: description(charge),
                metadata: {
                  kind: "top_up_charge",
                  top_up_charge_id: charge.id,
                  organization_id: charge.organizationId,
                  reason: charge.reason,
                },
              },
              key("invoice"),
            );
        if (!invoiceId) {
          invoiceId = invoice.id;
          await onInvoice(invoice.id);
        }

        if (invoice.status === "draft") {
          await stripe.invoiceItems.create(
            {
              customer: charge.stripeCustomerId,
              invoice: invoice.id,
              amount: nanoUsdToCents(charge.amount),
              currency: "usd",
              description: description(charge),
            },
            key("item"),
          );
          invoice = await stripe.invoices.finalizeInvoice(
            invoice.id,
            { auto_advance: false },
            key("finalize"),
          );
        }

        if (invoice.status === "open") {
          invoice = await stripe.invoices.pay(
            invoice.id,
            { payment_method: charge.stripePaymentMethodId, off_session: true },
            key("pay"),
          );
        }

        return (
          settledOutcome(invoice) ?? {
            status: "processing",
            stripeInvoiceId: invoice.id,
          }
        );
      } catch (error) {
        if (!isFinalStripeError(error)) throw error;

        await discard(invoiceId);

        return {
          status: "failed",
          failure: error.message,
          code: error.code ?? error.type,
        };
      }
    },

    async resolve(charge) {
      if (charge.stripeInvoiceId) {
        const invoice = await stripe.invoices.retrieve(charge.stripeInvoiceId);
        const outcome = settledOutcome(invoice);
        if (outcome) return outcome;

        await discard(invoice);
      }

      return {
        status: "failed",
        failure: "The payment could not be confirmed.",
        code: "expired",
      };
    },
  };
};

export const settleTopUpCharge = async (
  {
    store,
    charger,
    now,
  }: {
    store: Pick<TopUpChargeStore, "recordInvoice" | "succeed" | "fail">;
    charger: TopUpCharger;
    now: Date;
  },
  charge: TopUpChargeRecord,
): Promise<TopUpChargeOutcome> => {
  const expired =
    now.getTime() - charge.createdAt.getTime() > PENDING_EXPIRY_MILLISECONDS;
  const outcome = expired
    ? await charger.resolve(charge)
    : await charger.charge(charge, (invoiceId) =>
        store.recordInvoice(charge.id, invoiceId),
      );

  if (outcome.status === "succeeded") {
    await store.succeed({
      chargeId: charge.id,
      stripeInvoiceId: outcome.stripeInvoiceId,
      amount: outcome.amount,
    });
  }

  if (outcome.status === "failed") {
    await store.fail({ chargeId: charge.id, failure: outcome.failure });
  }

  return outcome;
};
