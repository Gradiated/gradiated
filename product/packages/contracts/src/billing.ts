import { z } from "@hono/zod-openapi";

import {
  MoneySchema,
  pageFields,
  TimestampSchema,
  UuidSchema,
} from "./common.js";

const MIN_TOP_UP_NANO_USD = 5_000_000_000n;
const MAX_TOP_UP_NANO_USD = 10_000_000_000_000n;
const NANO_USD_PER_CENT = 10_000_000n;

export const CreateTopUpCheckoutSchema = z
  .strictObject({
    amount: MoneySchema.refine((value) => {
      const amount = BigInt(value);

      return (
        amount >= MIN_TOP_UP_NANO_USD &&
        amount <= MAX_TOP_UP_NANO_USD &&
        amount % NANO_USD_PER_CENT === 0n
      );
    }, "Amount must be between $5 and $10,000 in whole cents.").openapi({
      description: "The top-up amount in integer nano-USD.",
      example: "50000000000",
    }),
  })
  .openapi("CreateTopUpCheckout");

export const TopUpCheckoutSchema = z
  .strictObject({ checkout_url: z.url() })
  .openapi("TopUpCheckout");

export const StripeWebhookHeadersSchema = z.object({
  "stripe-signature": z.string().min(1),
});

export const StripeWebhookPayloadSchema = z.unknown().openapi({
  type: "object",
  description: "The raw, signed Stripe event payload.",
});

export const StripeWebhookResponseSchema = z
  .strictObject({ received: z.literal(true) })
  .openapi("StripeWebhookResponse");

export const BillingAccountSchema = z
  .strictObject({
    organization_id: UuidSchema,
    mode: z.enum(["prepaid", "invoiced"]),
    balance: MoneySchema,
    created_at: TimestampSchema,
    updated_at: TimestampSchema,
  })
  .openapi("BillingAccount");

export const BalanceTransactionSchema = z
  .strictObject({
    id: UuidSchema,
    organization_id: UuidSchema,
    type: z.enum([
      "topup",
      "usage",
      "refund",
      "chargeback",
      "credit",
      "payment",
      "adjustment",
    ]),
    amount: MoneySchema,
    balance_after: MoneySchema,
    source_type: z.enum([
      "stripe_checkout_session",
      "stripe_refund",
      "stripe_dispute",
      "generation_settlement_batch",
      "openrouter_payment",
      "operator",
    ]),
    period_start: TimestampSchema.nullable(),
    period_end: TimestampSchema.nullable(),
    generation_count: MoneySchema.nullable(),
    created_at: TimestampSchema,
  })
  .openapi("BalanceTransaction");

export const BalanceTransactionListSchema = z
  .strictObject(pageFields(BalanceTransactionSchema))
  .openapi("BalanceTransactionList");

export type BalanceTransaction = z.infer<typeof BalanceTransactionSchema>;
export type BillingAccount = z.infer<typeof BillingAccountSchema>;
export type CreateTopUpCheckout = z.infer<typeof CreateTopUpCheckoutSchema>;
