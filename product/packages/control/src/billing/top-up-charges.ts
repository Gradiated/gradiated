import { UuidSchema } from "@gradiated/contracts";
import {
  and,
  asc,
  count,
  desc,
  eq,
  gte,
  inArray,
  isNull,
  lt,
  min,
  ne,
  or,
} from "drizzle-orm";
import { v7 as uuidv7 } from "uuid";
import { z } from "zod";

import type { ControlDatabase } from "../db/client.js";
import {
  TOP_UP_CHARGE_REASONS,
  TOP_UP_CHARGE_STATUSES,
  TOP_UP_METHODS,
  balanceTransactions,
  billingAccounts,
  topUpCharges,
  topUpRequests,
  organizations,
} from "../db/schema/index.js";
import { ControlServiceError } from "../errors.js";
import { requireRow } from "../require-row.js";
import { paymentMethodPatch, StripeIdSchema } from "./accounts.js";
import { postBalanceTransaction, type LedgerExecutor } from "./ledger.js";

const TopUpChargeRecordSchema = z.object({
  id: UuidSchema,
  organizationId: UuidSchema,
  reason: z.enum(TOP_UP_CHARGE_REASONS),
  status: z.enum(TOP_UP_CHARGE_STATUSES),
  amount: z.bigint().positive(),
  stripeCustomerId: StripeIdSchema,
  stripePaymentMethodId: StripeIdSchema,
  stripeInvoiceId: StripeIdSchema.nullable(),
  failure: z.string().nullable(),
  requestKey: z.string().min(1).max(255).nullable(),
  createdBy: UuidSchema.nullable(),
  createdAt: z.date(),
  updatedAt: z.date(),
});

export type TopUpChargeRecord = z.infer<typeof TopUpChargeRecordSchema>;

const parseCharge = (row: unknown): TopUpChargeRecord =>
  TopUpChargeRecordSchema.parse(row);

const ChargePatchSchema = TopUpChargeRecordSchema.pick({
  status: true,
  stripeInvoiceId: true,
  failure: true,
  updatedAt: true,
}).partial();

const chargePatch = (patch: z.input<typeof ChargePatchSchema>) =>
  ChargePatchSchema.parse(patch);

const TopUpRequestSchema = z.object({
  organizationId: UuidSchema,
  requestKey: z.string().min(1).max(255),
  method: z.enum(TOP_UP_METHODS),
  amount: z.bigint().positive(),
  requestedBy: UuidSchema.nullable(),
  replacesPaymentMethodId: StripeIdSchema.nullable(),
});

export type TopUpRequest = z.infer<typeof TopUpRequestSchema>;

const StoredTopUpRequestSchema = TopUpRequestSchema.extend({
  createdAt: z.date(),
});

export type LedgerCredit = { id: string; amount: bigint; createdAt: Date };

// Returns the organization's synchronous balance, or null when no gateway has
// seeded one and the posted PostgreSQL balance is therefore current.
export type OperationalBalanceReader = (
  organizationId: string,
  creditsSince: (since: Date) => Promise<LedgerCredit[]>,
) => Promise<bigint | null>;

export type AutoTopUpClaim =
  | { status: "claimed"; charge: TopUpChargeRecord }
  | { status: "rate_limited" }
  | { status: "not_due" };

export interface TopUpChargeStore {
  listAutoTopUpOrganizationIds(): Promise<string[]>;
  listPendingBefore(createdBefore: Date): Promise<TopUpChargeRecord[]>;
  oldestPendingCreatedAt(): Promise<Date | null>;
  claimAutoTopUp(
    organizationId: string,
    operationalBalance: OperationalBalanceReader,
    limits: { maxPerHour: number; now: Date },
  ): Promise<AutoTopUpClaim>;
  // A request key makes a retried request return its first charge.
  claimTopUp(input: {
    organizationId: string;
    userId: string;
    amount: bigint;
    requestKey?: string;
  }): Promise<{ charge: TopUpChargeRecord; replayed: boolean }>;
  // Stores a keyed request's method and amount, or returns those it was
  // first made with.
  recordRequest(
    request: TopUpRequest,
  ): Promise<TopUpRequest & { createdAt: Date }>;
  abandonInactive(createdBefore: Date): Promise<number>;
  recordInvoice(chargeId: string, stripeInvoiceId: string): Promise<void>;
  succeed(input: {
    chargeId: string;
    stripeInvoiceId: string;
    amount: bigint;
  }): Promise<void>;
  fail(input: { chargeId: string; failure: string }): Promise<void>;
}

const lockCharge = async (executor: LedgerExecutor, chargeId: string) => {
  const [row] = await executor
    .select()
    .from(topUpCharges)
    .where(eq(topUpCharges.id, chargeId))
    .for("update")
    .limit(1);

  return row ? parseCharge(row) : null;
};

const lockPrepaidAccount = async (
  executor: LedgerExecutor,
  organizationId: string,
) => {
  const [account] = await executor
    .select({
      balance: billingAccounts.balance,
      mode: billingAccounts.mode,
      stripeCustomerId: billingAccounts.stripeCustomerId,
      stripePaymentMethodId: billingAccounts.stripePaymentMethodId,
      autoTopUpEnabled: billingAccounts.autoTopUpEnabled,
      autoTopUpThreshold: billingAccounts.autoTopUpThreshold,
      autoTopUpAmount: billingAccounts.autoTopUpAmount,
      organizationStatus: organizations.status,
    })
    .from(billingAccounts)
    .innerJoin(
      organizations,
      eq(organizations.id, billingAccounts.organizationId),
    )
    .where(eq(billingAccounts.organizationId, organizationId))
    .for("update", { of: billingAccounts })
    .limit(1);

  return account?.mode === "prepaid" &&
    account.organizationStatus === "active" &&
    account.stripeCustomerId &&
    account.stripePaymentMethodId
    ? {
        ...account,
        stripeCustomerId: account.stripeCustomerId,
        stripePaymentMethodId: account.stripePaymentMethodId,
      }
    : null;
};

const hasPendingCharge = async (
  executor: LedgerExecutor,
  organizationId: string,
) => {
  const [pending] = await executor
    .select({ id: topUpCharges.id })
    .from(topUpCharges)
    .where(
      and(
        eq(topUpCharges.organizationId, organizationId),
        eq(topUpCharges.status, "pending"),
      ),
    )
    .limit(1);

  return Boolean(pending);
};

const insertCharge = async (
  executor: LedgerExecutor,
  fields: Pick<
    TopUpChargeRecord,
    | "organizationId"
    | "reason"
    | "amount"
    | "stripeCustomerId"
    | "stripePaymentMethodId"
    | "createdBy"
  > &
    Partial<Pick<TopUpChargeRecord, "requestKey">>,
) => {
  const now = new Date();
  const charge = parseCharge({
    ...fields,
    id: uuidv7(),
    status: "pending",
    stripeInvoiceId: null,
    failure: null,
    requestKey: fields.requestKey ?? null,
    createdAt: now,
    updatedAt: now,
  });

  return parseCharge(
    requireRow(
      await executor.insert(topUpCharges).values(charge).returning(),
      "The top-up charge insert returned no row.",
    ),
  );
};

export const createTopUpChargeStore = (
  database: ControlDatabase,
): TopUpChargeStore => ({
  async listAutoTopUpOrganizationIds() {
    const rows = await database
      .select({ organizationId: billingAccounts.organizationId })
      .from(billingAccounts)
      .innerJoin(
        organizations,
        eq(organizations.id, billingAccounts.organizationId),
      )
      .where(
        and(
          eq(billingAccounts.autoTopUpEnabled, true),
          eq(organizations.status, "active"),
        ),
      );

    return rows.map((row) => row.organizationId);
  },

  async listPendingBefore(createdBefore) {
    const rows = await database
      .select()
      .from(topUpCharges)
      .where(
        and(
          eq(topUpCharges.status, "pending"),
          lt(topUpCharges.createdAt, createdBefore),
        ),
      )
      .orderBy(asc(topUpCharges.createdAt));

    return rows.map(parseCharge);
  },

  async oldestPendingCreatedAt() {
    const [row] = await database
      .select({ createdAt: min(topUpCharges.createdAt) })
      .from(topUpCharges)
      .where(eq(topUpCharges.status, "pending"));

    return row?.createdAt ?? null;
  },

  async claimAutoTopUp(organizationId, operationalBalance, limits) {
    return database.transaction(async (transaction) => {
      // Every ledger writer takes this lock, so no credit can land between the
      // ledger read and the operational balance snapshot.
      const account = await lockPrepaidAccount(transaction, organizationId);
      if (
        !account?.autoTopUpEnabled ||
        account.autoTopUpThreshold === null ||
        account.autoTopUpAmount === null ||
        (await hasPendingCharge(transaction, organizationId))
      ) {
        return { status: "not_due" };
      }

      const balance =
        (await operationalBalance(organizationId, (since) =>
          transaction
            .select({
              id: balanceTransactions.id,
              amount: balanceTransactions.amount,
              createdAt: balanceTransactions.createdAt,
            })
            .from(balanceTransactions)
            .where(
              and(
                eq(balanceTransactions.organizationId, organizationId),
                gte(balanceTransactions.createdAt, since),
                ne(
                  balanceTransactions.sourceType,
                  "generation_settlement_batch",
                ),
              ),
            ),
        )) ?? account.balance;
      if (balance >= account.autoTopUpThreshold) return { status: "not_due" };

      const [recent] = await transaction
        .select({ charges: count() })
        .from(topUpCharges)
        .where(
          and(
            eq(topUpCharges.organizationId, organizationId),
            eq(topUpCharges.reason, "auto_top_up"),
            inArray(topUpCharges.status, ["pending", "succeeded"]),
            gte(
              topUpCharges.createdAt,
              new Date(limits.now.getTime() - 60 * 60_000),
            ),
          ),
        );
      if ((recent?.charges ?? 0) >= limits.maxPerHour) {
        return { status: "rate_limited" };
      }

      return {
        status: "claimed",
        charge: await insertCharge(transaction, {
          organizationId,
          reason: "auto_top_up",
          amount: account.autoTopUpAmount,
          stripeCustomerId: account.stripeCustomerId,
          stripePaymentMethodId: account.stripePaymentMethodId,
          createdBy: null,
        }),
      };
    });
  },

  async claimTopUp({ organizationId, userId, amount, requestKey }) {
    return database.transaction(async (transaction) => {
      const account = await lockPrepaidAccount(transaction, organizationId);
      const [previous] = requestKey
        ? await transaction
            .select()
            .from(topUpCharges)
            .where(
              and(
                eq(topUpCharges.organizationId, organizationId),
                eq(topUpCharges.requestKey, requestKey),
              ),
            )
            .limit(1)
        : [];
      if (previous) {
        const charge = parseCharge(previous);
        if (charge.amount !== amount) {
          throw new ControlServiceError(
            "conflict",
            "This request key was used for a different amount.",
          );
        }

        return { charge, replayed: true };
      }

      if (!account) {
        throw new ControlServiceError(
          "conflict",
          "Save a card before topping up with it.",
        );
      }

      if (await hasPendingCharge(transaction, organizationId)) {
        throw new ControlServiceError(
          "conflict",
          "Another payment is still in progress. Try again in a minute.",
        );
      }

      const charge = await insertCharge(transaction, {
        organizationId,
        reason: "top_up",
        amount,
        stripeCustomerId: account.stripeCustomerId,
        stripePaymentMethodId: account.stripePaymentMethodId,
        createdBy: userId,
        ...(requestKey ? { requestKey } : {}),
      });

      return { charge, replayed: false };
    });
  },

  // A charge that never reached Stripe is not retried once its organization
  // is suspended or no longer prepaid; invoiced charges still reconcile.
  async abandonInactive(createdBefore) {
    const inactive = await database
      .select({ id: topUpCharges.id })
      .from(topUpCharges)
      .innerJoin(
        organizations,
        eq(organizations.id, topUpCharges.organizationId),
      )
      .innerJoin(
        billingAccounts,
        eq(billingAccounts.organizationId, topUpCharges.organizationId),
      )
      .where(
        and(
          eq(topUpCharges.status, "pending"),
          isNull(topUpCharges.stripeInvoiceId),
          lt(topUpCharges.createdAt, createdBefore),
          or(
            ne(organizations.status, "active"),
            ne(billingAccounts.mode, "prepaid"),
          ),
        ),
      );
    if (!inactive.length) return 0;

    const abandoned = await database
      .update(topUpCharges)
      .set(
        chargePatch({
          status: "failed",
          failure: "The organization is no longer active.",
          updatedAt: new Date(),
        }),
      )
      .where(
        and(
          inArray(
            topUpCharges.id,
            inactive.map((row) => row.id),
          ),
          eq(topUpCharges.status, "pending"),
          isNull(topUpCharges.stripeInvoiceId),
        ),
      )
      .returning({ id: topUpCharges.id });

    return abandoned.length;
  },

  async recordRequest(request) {
    const values = TopUpRequestSchema.parse(request);
    await database.insert(topUpRequests).values(values).onConflictDoNothing();

    const [stored] = await database
      .select({
        organizationId: topUpRequests.organizationId,
        requestKey: topUpRequests.requestKey,
        method: topUpRequests.method,
        amount: topUpRequests.amount,
        requestedBy: topUpRequests.requestedBy,
        replacesPaymentMethodId: topUpRequests.replacesPaymentMethodId,
        createdAt: topUpRequests.createdAt,
      })
      .from(topUpRequests)
      .where(
        and(
          eq(topUpRequests.organizationId, values.organizationId),
          eq(topUpRequests.requestKey, values.requestKey),
        ),
      )
      .limit(1);

    return StoredTopUpRequestSchema.parse(stored);
  },

  async recordInvoice(chargeId, stripeInvoiceId) {
    await database
      .update(topUpCharges)
      .set(chargePatch({ stripeInvoiceId, updatedAt: new Date() }))
      .where(eq(topUpCharges.id, chargeId));
  },

  async succeed({ chargeId, stripeInvoiceId, amount }) {
    await database.transaction(async (transaction) => {
      const charge = await lockCharge(transaction, chargeId);
      if (!charge || charge.status === "succeeded") return;

      const patch = chargePatch({
        status: "succeeded",
        stripeInvoiceId,
        failure: null,
        updatedAt: new Date(),
      });
      if (charge.amount !== amount) {
        throw new Error(
          `Top-up charge ${chargeId} was paid ${amount}, not ${charge.amount}.`,
        );
      }

      await postBalanceTransaction(transaction, {
        organizationId: charge.organizationId,
        type: "topup",
        amount,
        sourceType: "stripe_invoice",
        sourceId: stripeInvoiceId,
        createdBy: charge.createdBy,
      });
      await transaction
        .update(topUpCharges)
        .set(patch)
        .where(eq(topUpCharges.id, chargeId));
    });
  },

  async fail({ chargeId, failure }) {
    await database.transaction(async (transaction) => {
      const charge = await lockCharge(transaction, chargeId);
      if (charge?.status !== "pending") return;

      const now = new Date();

      await transaction
        .update(topUpCharges)
        .set(chargePatch({ status: "failed", failure, updatedAt: now }))
        .where(eq(topUpCharges.id, chargeId));

      if (charge.reason === "auto_top_up") {
        await transaction
          .update(billingAccounts)
          .set(paymentMethodPatch({ autoTopUpEnabled: false, updatedAt: now }))
          .where(eq(billingAccounts.organizationId, charge.organizationId));
      }
    });
  },
});

export type TopUpStatus = {
  pending: boolean;
  autoTopUpFailure: string | null;
};

// Whether a charge is still settling, and Stripe's reason when the latest
// auto top-up charge failed.
export const topUpStatus = async (
  database: ControlDatabase,
  organizationId: string,
): Promise<TopUpStatus> => {
  const [pending, latestAuto, settings] = await Promise.all([
    hasPendingCharge(database, organizationId),
    database
      .select()
      .from(topUpCharges)
      .where(
        and(
          eq(topUpCharges.organizationId, organizationId),
          eq(topUpCharges.reason, "auto_top_up"),
        ),
      )
      .orderBy(desc(topUpCharges.createdAt))
      .limit(1),
    database
      .select({ updatedAt: billingAccounts.autoTopUpUpdatedAt })
      .from(billingAccounts)
      .where(eq(billingAccounts.organizationId, organizationId))
      .limit(1),
  ]);
  const [row] = latestAuto;
  const charge = row ? parseCharge(row) : null;
  const settingsUpdatedAt = z
    .date()
    .nullable()
    .parse(settings[0]?.updatedAt ?? null);
  // Saving the settings after a failure acknowledges it.
  const acknowledged =
    charge !== null &&
    settingsUpdatedAt !== null &&
    settingsUpdatedAt > charge.updatedAt;

  return {
    pending,
    autoTopUpFailure:
      charge?.status === "failed" && !acknowledged ? charge.failure : null,
  };
};
