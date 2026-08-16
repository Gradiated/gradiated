import { z } from "@hono/zod-openapi";

import { TimestampSchema, UuidSchema } from "./common.js";

const MoneySchema = z.string().regex(/^-?\d+$/);
const NanoUsdPerCent = 10_000_000n;

export const CreateTopUpCheckoutSchema = z
  .strictObject({
    amount: MoneySchema.refine((value) => {
      const amount = BigInt(value);
      return (
        amount >= 5_000_000_000n &&
        amount <= 10_000_000_000_000n &&
        amount % NanoUsdPerCent === 0n
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
  .strictObject({
    data: z.array(BalanceTransactionSchema),
    next_cursor: z.string().nullable(),
  })
  .openapi("BalanceTransactionList");

export type BalanceTransaction = z.infer<typeof BalanceTransactionSchema>;
export type BillingAccount = z.infer<typeof BillingAccountSchema>;
export type CreateTopUpCheckout = z.infer<typeof CreateTopUpCheckoutSchema>;
