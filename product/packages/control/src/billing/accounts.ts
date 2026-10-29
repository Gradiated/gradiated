import { UuidSchema, type UpdateAutoTopUp } from "@gradiated/contracts";
import { and, eq, isNull, or, sql } from "drizzle-orm";
import { z } from "zod";

import type { ControlDatabase } from "../db/client.js";
import { BILLING_MODES, billingAccounts } from "../db/schema/index.js";
import { ControlServiceError } from "../errors.js";
import { billingAccountNotFound, type LedgerExecutor } from "./ledger.js";

export const StripeIdSchema = z.string().min(1).max(255);

const BillingAccountRecordSchema = z.object({
  organizationId: UuidSchema,
  mode: z.enum(BILLING_MODES),
  stripeCustomerId: StripeIdSchema.nullable(),
  balance: z.bigint(),
  stripePaymentMethodId: StripeIdSchema.nullable(),
  autoTopUpEnabled: z.boolean(),
  autoTopUpThreshold: z.bigint().nonnegative().nullable(),
  autoTopUpAmount: z.bigint().positive().nullable(),
  createdAt: z.date(),
  updatedAt: z.date(),
});

export type BillingAccountRecord = z.infer<typeof BillingAccountRecordSchema>;

const AutoTopUpPatchSchema = z
  .object({
    autoTopUpEnabled: z.boolean(),
    autoTopUpThreshold: z.bigint().nonnegative(),
    autoTopUpAmount: z.bigint().positive(),
  })
  .partial()
  .extend({ autoTopUpUpdatedAt: z.date(), updatedAt: z.date() });

// Every write to the Stripe customer, saved card or auto top-up switch
// outside the settings update is parsed whole.
const PaymentMethodPatchSchema = z
  .object({
    stripeCustomerId: StripeIdSchema,
    stripePaymentMethodId: StripeIdSchema.nullable(),
    autoTopUpEnabled: z.literal(false),
  })
  .partial()
  .extend({ updatedAt: z.date() });

export const paymentMethodPatch = (
  patch: z.input<typeof PaymentMethodPatchSchema>,
) => PaymentMethodPatchSchema.parse(patch);

const SavedCardPatchSchema = PaymentMethodPatchSchema.required({
  stripeCustomerId: true,
  stripePaymentMethodId: true,
}).extend({ stripePaymentMethodId: StripeIdSchema });

const parseAccount = (row: unknown) => BillingAccountRecordSchema.parse(row);

export const readBillingAccount = async (
  executor: LedgerExecutor | ControlDatabase,
  organizationId: string,
  lock = false,
): Promise<BillingAccountRecord> => {
  const query = executor
    .select()
    .from(billingAccounts)
    .where(eq(billingAccounts.organizationId, organizationId))
    .limit(1);
  const [row] = lock ? await query.for("update") : await query;
  if (!row) throw billingAccountNotFound();

  return parseAccount(row);
};

// Reads and writes under the row lock, and writes only the settings supplied,
// so a concurrent decline that turns auto top-up off is never overwritten.
export const updateAutoTopUpSettings = (
  database: ControlDatabase,
  organizationId: string,
  settings: UpdateAutoTopUp,
): Promise<BillingAccountRecord> =>
  database.transaction(async (transaction) => {
    const current = await readBillingAccount(transaction, organizationId, true);
    if (current.mode !== "prepaid") {
      throw new ControlServiceError(
        "conflict",
        "Auto top-up is only available for prepaid organizations.",
      );
    }

    // Only supplied settings are written; validation sees the result.
    const now = new Date();
    const patch = AutoTopUpPatchSchema.parse({
      ...(settings.enabled === undefined
        ? {}
        : { autoTopUpEnabled: settings.enabled }),
      ...(settings.threshold === undefined
        ? {}
        : { autoTopUpThreshold: BigInt(settings.threshold) }),
      ...(settings.amount === undefined
        ? {}
        : { autoTopUpAmount: BigInt(settings.amount) }),
      autoTopUpUpdatedAt: now,
      updatedAt: now,
    });
    const next = { ...current, ...patch };
    if (next.autoTopUpEnabled && !next.stripePaymentMethodId) {
      throw new ControlServiceError(
        "conflict",
        "Save a card before turning on auto top-up.",
      );
    }

    if (
      next.autoTopUpEnabled &&
      (next.autoTopUpThreshold === null || next.autoTopUpAmount === null)
    ) {
      throw new ControlServiceError(
        "conflict",
        "Set a threshold and an amount before turning on auto top-up.",
      );
    }

    const [updated] = await transaction
      .update(billingAccounts)
      .set(patch)
      .where(eq(billingAccounts.organizationId, organizationId))
      .returning();
    if (!updated) throw billingAccountNotFound();

    return parseAccount(updated);
  });

// Saves the payment method for the account's Stripe customer. With `replacing`,
// it saves only while that is still the saved method, so a late event cannot
// overwrite a newer card. Returns whether the method was saved.
export const savePaymentMethod = async (
  database: ControlDatabase,
  input: {
    organizationId: string;
    stripeCustomerId: string;
    stripePaymentMethodId: string;
    replacing?: string | null;
  },
): Promise<boolean> => {
  const patch = SavedCardPatchSchema.parse({
    stripeCustomerId: input.stripeCustomerId,
    stripePaymentMethodId: input.stripePaymentMethodId,
    updatedAt: new Date(),
  });
  const [current] = await database
    .select({ stripeCustomerId: billingAccounts.stripeCustomerId })
    .from(billingAccounts)
    .where(eq(billingAccounts.organizationId, input.organizationId))
    .limit(1);
  if (!current) throw billingAccountNotFound();

  if (
    current.stripeCustomerId &&
    current.stripeCustomerId !== patch.stripeCustomerId
  ) {
    throw new ControlServiceError(
      "conflict",
      "The card belongs to a different Stripe customer.",
    );
  }

  const updated = await database
    .update(billingAccounts)
    .set(patch)
    .where(
      and(
        eq(billingAccounts.organizationId, input.organizationId),
        or(
          isNull(billingAccounts.stripeCustomerId),
          eq(billingAccounts.stripeCustomerId, patch.stripeCustomerId),
        ),
        // Saving the card already saved also succeeds, so a retried event
        // still gets to set it as the Stripe default.
        input.replacing === undefined
          ? undefined
          : or(
              sql`${billingAccounts.stripePaymentMethodId} is not distinct from ${input.replacing}`,
              eq(
                billingAccounts.stripePaymentMethodId,
                patch.stripePaymentMethodId,
              ),
            ),
      ),
    )
    .returning({ organizationId: billingAccounts.organizationId });

  return updated.length > 0;
};

export const savedPaymentMethod = async (
  database: ControlDatabase,
  organizationId: string,
): Promise<string | null> => {
  const [account] = await database
    .select({ stripePaymentMethodId: billingAccounts.stripePaymentMethodId })
    .from(billingAccounts)
    .where(eq(billingAccounts.organizationId, organizationId))
    .limit(1);
  if (!account) throw billingAccountNotFound();

  return StripeIdSchema.nullable().parse(account.stripePaymentMethodId);
};

export const updateCustomerPaymentMethod = async (
  database: ControlDatabase,
  input: { stripeCustomerId: string; stripePaymentMethodId: string },
): Promise<void> => {
  await database
    .update(billingAccounts)
    .set(
      paymentMethodPatch({
        stripePaymentMethodId: input.stripePaymentMethodId,
        updatedAt: new Date(),
      }),
    )
    .where(
      eq(
        billingAccounts.stripeCustomerId,
        StripeIdSchema.parse(input.stripeCustomerId),
      ),
    );
};

// A customer whose default card was removed in Stripe has no card to charge,
// so the saved card and auto top-up are cleared together.
export const clearCustomerPaymentMethod = async (
  database: ControlDatabase,
  stripeCustomerId: string,
): Promise<void> => {
  const customer = StripeIdSchema.parse(stripeCustomerId);

  await database
    .update(billingAccounts)
    .set(
      paymentMethodPatch({
        stripePaymentMethodId: null,
        autoTopUpEnabled: false,
        updatedAt: new Date(),
      }),
    )
    .where(eq(billingAccounts.stripeCustomerId, customer));
};

// Binds a Stripe customer to an account without one and returns the account's
// customer, which is the earlier one if another request bound it first.
export const bindStripeCustomer = async (
  executor: LedgerExecutor | ControlDatabase,
  organizationId: string,
  stripeCustomerId: string,
): Promise<string> => {
  const patch = paymentMethodPatch({ stripeCustomerId, updatedAt: new Date() });

  const [bound] = await executor
    .update(billingAccounts)
    .set(patch)
    .where(
      and(
        eq(billingAccounts.organizationId, organizationId),
        isNull(billingAccounts.stripeCustomerId),
      ),
    )
    .returning({ stripeCustomerId: billingAccounts.stripeCustomerId });
  if (bound?.stripeCustomerId) return bound.stripeCustomerId;

  // Another request bound first; its customer stands.
  const account = await readBillingAccount(executor, organizationId);

  return account.stripeCustomerId ?? StripeIdSchema.parse(stripeCustomerId);
};
