import { z } from "@hono/zod-openapi";

import {
  MoneySchema,
  pageFields,
  TimestampSchema,
  UuidSchema,
} from "./common.js";

export const NANO_USD_PER_USD = 1_000_000_000n;
export const NANO_USD_PER_CENT = NANO_USD_PER_USD / 100n;
export const MIN_TOP_UP_NANO_USD = 5n * NANO_USD_PER_USD;
export const MAX_TOP_UP_NANO_USD = 10_000n * NANO_USD_PER_USD;

// Stripe amounts are integer cents; the ledger counts nano-USD.
export const centsToNanoUsd = (cents: number): bigint =>
  BigInt(cents) * NANO_USD_PER_CENT;
export const nanoUsdToCents = (nanoUsd: bigint): number =>
  Number(nanoUsd / NANO_USD_PER_CENT);

const centsBetween = (minimum: bigint, maximum: bigint) => (value: string) => {
  const amount = BigInt(value);

  return (
    amount >= minimum && amount <= maximum && amount % NANO_USD_PER_CENT === 0n
  );
};

const TopUpAmountSchema = MoneySchema.refine(
  centsBetween(MIN_TOP_UP_NANO_USD, MAX_TOP_UP_NANO_USD),
  "Amount must be between $5 and $10,000 in whole cents.",
);

export const CreateTopUpSchema = z
  .strictObject({
    amount: TopUpAmountSchema.openapi({
      description: "The top-up amount in integer nano-USD.",
      example: "50000000000",
    }),
    method: z
      .enum(["card", "checkout"])
      .optional()
      .describe(
        "card charges the saved card; checkout opens Stripe Checkout. Defaults to card when one is saved.",
      ),
    idempotency_key: UuidSchema.optional().describe(
      "A key for one top-up attempt; retrying it returns the first result instead of charging again.",
    ),
  })
  .openapi("CreateTopUp");

export const UpdateAutoTopUpSchema = z
  .strictObject({
    enabled: z
      .boolean()
      .describe(
        "Charge the saved card whenever the balance falls below the threshold.",
      ),
    threshold: MoneySchema.refine(
      centsBetween(0n, MAX_TOP_UP_NANO_USD),
      "Threshold must be between $0 and $10,000 in whole cents.",
    ).openapi({
      description:
        "Top up when the balance falls below this integer nano-USD amount.",
      example: "10000000000",
    }),
    amount: TopUpAmountSchema.openapi({
      description: "The integer nano-USD amount each top-up adds.",
      example: "50000000000",
    }),
  })
  .partial()
  .refine(
    (settings) => Object.keys(settings).length > 0,
    "Provide at least one auto top-up setting.",
  )
  .openapi("UpdateAutoTopUp");

export const UpdateBillingAccountSchema = z
  .strictObject({ auto_top_up: UpdateAutoTopUpSchema })
  .openapi("UpdateBillingAccount");

export const PaymentMethodSessionSchema = z
  .strictObject({
    url: z
      .url()
      .describe("The Stripe billing portal, for invoices and billing details."),
  })
  .openapi("PaymentMethodSession");

export const CardSetupSchema = z
  .strictObject({
    client_secret: z
      .string()
      .min(1)
      .describe("Client secret of a card-only Stripe SetupIntent."),
    publishable_key: z
      .string()
      .min(1)
      .describe("Stripe publishable key that loads Stripe.js."),
  })
  .openapi("CardSetup");

export const SaveCardSchema = z
  .strictObject({
    setup_intent_id: z
      .string()
      .min(1)
      .max(255)
      .describe("The SetupIntent that Stripe.js confirmed."),
  })
  .openapi("SaveCard");

export const TopUpSchema = z
  .strictObject({
    status: z
      .enum(["paid", "processing", "checkout"])
      .describe(
        "paid when the card was charged, processing while Stripe confirms it, checkout when payment continues at checkout_url.",
      ),
    checkout_url: z.url().nullable(),
  })
  .openapi("TopUp");

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

export const PaymentMethodSchema = z
  .strictObject({
    brand: z
      .string()
      .nullable()
      .describe(
        "The card brand, such as visa; null when Stripe could not be reached.",
      ),
    last4: z
      .string()
      .nullable()
      .describe(
        "The last four digits of the card; null when Stripe could not be reached.",
      ),
    exp_month: z.number().int().min(1).max(12).nullable(),
    exp_year: z.number().int().nullable(),
  })
  .describe("The saved card, read from Stripe; Gradiated stores only its ID.")
  .openapi("PaymentMethod");

export const AutoTopUpSchema = z
  .strictObject({
    enabled: z.boolean(),
    threshold: MoneySchema.nullable(),
    amount: MoneySchema.nullable(),
    failure: z
      .string()
      .nullable()
      .describe(
        "Stripe's reason when the latest auto top-up charge failed, which turned auto top-up off.",
      ),
  })
  .openapi("AutoTopUp");

export const BillingAccountSchema = z
  .strictObject({
    organization_id: UuidSchema,
    mode: z.enum(["prepaid", "invoiced"]),
    balance: MoneySchema,
    payment_method: PaymentMethodSchema.nullable().describe(
      "The saved card used for top-ups and auto top-up.",
    ),
    auto_top_up: AutoTopUpSchema,
    top_up_pending: z
      .boolean()
      .describe(
        "Whether a saved-card top-up is still waiting for Stripe; clients can poll until it settles.",
      ),
    billing_portal: z
      .boolean()
      .describe(
        "Whether the Stripe billing portal has invoices and billing details to show.",
      ),
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
      "stripe_invoice",
    ]),
    stripe_id: z
      .string()
      .nullable()
      .describe(
        "The Stripe Checkout Session, invoice, refund or dispute behind the transaction.",
      ),
    period_start: TimestampSchema.nullable(),
    period_end: TimestampSchema.nullable(),
    generation_count: MoneySchema.nullable(),
    created_at: TimestampSchema,
  })
  .openapi("BalanceTransaction");

export const BalanceTransactionQuerySchema = z.object({
  limit: z.coerce
    .number()
    .int()
    .min(1)
    .max(100)
    .default(50)
    .describe("Maximum number of balance transactions to return."),
  cursor: UuidSchema.optional().describe(
    "Return transactions older than this transaction ID.",
  ),
});

export type BalanceTransactionQuery = z.infer<
  typeof BalanceTransactionQuerySchema
>;

export const BalanceTransactionListSchema = z
  .strictObject(pageFields(BalanceTransactionSchema))
  .openapi("BalanceTransactionList");

export type BalanceTransaction = z.infer<typeof BalanceTransactionSchema>;
export type BillingAccount = z.infer<typeof BillingAccountSchema>;
export type CreateTopUp = z.infer<typeof CreateTopUpSchema>;
export type UpdateAutoTopUp = z.infer<typeof UpdateAutoTopUpSchema>;
