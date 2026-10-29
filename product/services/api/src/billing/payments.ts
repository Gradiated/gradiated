import {
  centsToNanoUsd,
  CreateTopUpSchema,
  nanoUsdToCents,
} from "@gradiated/contracts";
import {
  ControlServiceError,
  settleTopUpCharge,
  type TopUpCharger,
  type TopUpChargeStore,
  type CatalogBillingService,
} from "@gradiated/control";
import { z } from "@hono/zod-openapi";

import { serviceLog } from "../logging.js";
import {
  stripeId,
  type SavedCard,
  type StripeGateway,
} from "./stripe-gateway.js";

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
      payment_intent: z
        .union([z.string(), z.object({ id: z.string() })])
        .nullable()
        .optional(),
      client_reference_id: z.string().nullable(),
      metadata: z.record(z.string(), z.string()).nullable(),
    }),
  }),
});

const TopUpMetadataSchema = z.object({
  kind: z.literal("balance_topup"),
  organization_id: z.uuid(),
  user_id: z.uuid(),
  // Empty when no card was saved as Checkout opened.
  replaces_payment_method: z.string().optional(),
});

const CustomerUpdatedEventSchema = z.object({
  type: z.literal("customer.updated"),
  data: z.object({
    object: z.object({
      id: z.string().min(1),
      invoice_settings: z.object({
        default_payment_method: z
          .union([z.string(), z.object({ id: z.string() })])
          .nullable(),
      }),
    }),
  }),
});

const TopUpChargeInvoiceEventSchema = z.object({
  type: z.literal("invoice.paid"),
  data: z.object({
    object: z.object({
      id: z.string().min(1),
      currency: z.string(),
      amount_paid: z.number().int().nonnegative(),
      metadata: z.object({
        kind: z.literal("top_up_charge"),
        top_up_charge_id: z.uuid(),
      }),
    }),
  }),
});

// A charge invoice whose payment failed after Stripe accepted it as pending.
const TopUpChargeInvoiceFailedEventSchema = z.object({
  type: z.literal("invoice.payment_failed"),
  data: z.object({
    object: z.object({
      id: z.string().min(1),
      metadata: z.object({
        kind: z.literal("top_up_charge"),
        top_up_charge_id: z.uuid(),
      }),
    }),
  }),
});

// A saved-card charge reports paid once Stripe settles it, else processing.
const cardResult = (
  status: "succeeded" | "pending" | "processing",
): Extract<TopUpResult, { checkoutUrl: null }> => ({
  status: status === "succeeded" ? "paid" : "processing",
  checkoutUrl: null,
});

type PaymentsUser = {
  userId: string;
  userEmail: string;
  organizationId: string;
};

export type CardDetails = Pick<
  SavedCard,
  "brand" | "last4" | "expMonth" | "expYear"
>;

// Card details are read from Stripe and cached briefly, never stored.
export type CardDetailsCache = {
  get(key: string): Promise<string | null>;
  set(key: string, value: string, options: { EX: number }): Promise<unknown>;
};

const CARD_DETAILS_TTL_SECONDS = 60;
const MISSING_CARD_TTL_SECONDS = 15;
// Bounds the passes that reconcile the saved card with Stripe's default.
const CARD_SYNC_ATTEMPTS = 3;
// Inside Stripe's 24-hour idempotency window, as Checkout Sessions also expire.
const CHECKOUT_REQUEST_LIFETIME_MS = 23 * 60 * 60_000;

const cardDetailsKey = (paymentMethodId: string) =>
  `stripe-card:{${paymentMethodId}}`;

const cardDetailsOf = ({
  brand,
  last4,
  expMonth,
  expYear,
}: SavedCard): CardDetails => ({ brand, last4, expMonth, expYear });

export type TopUpResult =
  | { status: "paid" | "processing"; checkoutUrl: null }
  | { status: "checkout"; checkoutUrl: string };

export interface BillingPaymentsService {
  createTopUp(
    input: PaymentsUser & {
      amount: bigint;
      method?: "card" | "checkout";
      requestKey?: string;
    },
  ): Promise<TopUpResult>;
  createPaymentMethodSession(input: PaymentsUser): Promise<{ url: string }>;
  createCardSetup(
    input: PaymentsUser,
  ): Promise<{ clientSecret: string; publishableKey: string }>;
  saveCard(input: PaymentsUser & { setupIntentId: string }): Promise<void>;
  describeCard(paymentMethodId: string): Promise<CardDetails | null>;
  handleWebhook(input: { payload: string; signature: string }): Promise<void>;
}

export class BillingPaymentsError extends Error {
  constructor(
    readonly code:
      | "invalid_webhook"
      | "not_prepaid"
      | "card_not_confirmed"
      | "no_billing_customer"
      | "payment_failed"
      | "provider_error"
      | "unavailable",
    message: string,
    override readonly cause?: unknown,
  ) {
    super(message);
    this.name = "BillingPaymentsError";
  }
}

const isTopUpAmount = (amount: bigint): boolean =>
  CreateTopUpSchema.shape.amount.safeParse(amount.toString()).success;

const TopUpEventSchema = z.object({
  type: StripeCheckoutEventSchema.shape.type,
  data: z.object({
    object: z.object({
      metadata: z.object({ kind: TopUpMetadataSchema.shape.kind }),
    }),
  }),
});

type StripeEventKind = "topup" | "top_up_charge";

type StripeEventRejection =
  "schema" | "metadata_mismatch" | "currency" | "amount_out_of_range";

const stripeEventRejection = (
  kind: StripeEventKind,
  reason: StripeEventRejection,
  cause?: unknown,
): BillingPaymentsError => {
  serviceLog(
    "error",
    `stripe_${kind}_rejected_${reason}`,
    cause === undefined ? {} : { error: cause },
  );

  return new BillingPaymentsError(
    "invalid_webhook",
    "The Stripe event is not valid for this account.",
    cause,
  );
};

export const createBillingPaymentsService = ({
  gateway,
  accounts,
  topUpCharges,
  charger,
  productUrl,
  publishableKey,
  cardDetails,
}: {
  gateway: StripeGateway;
  accounts: Pick<
    CatalogBillingService,
    | "getManagedBillingAccount"
    | "applyBalanceTransaction"
    | "savePaymentMethod"
    | "savedPaymentMethod"
    | "updateCustomerPaymentMethod"
    | "bindStripeCustomer"
    | "clearCustomerPaymentMethod"
  >;
  topUpCharges: Pick<
    TopUpChargeStore,
    "claimTopUp" | "recordRequest" | "recordInvoice" | "succeed" | "fail"
  >;
  charger: TopUpCharger;
  productUrl: string;
  publishableKey: string | undefined;
  cardDetails: CardDetailsCache;
}): BillingPaymentsService => {
  const baseProductUrl = productUrl.replace(/\/$/, "");

  const stripeCall = async <Result>(
    message: string,
    call: () => Promise<Result>,
  ): Promise<Result> => {
    try {
      return await call();
    } catch (error) {
      throw new BillingPaymentsError("provider_error", message, error);
    }
  };

  const prepaidAccount = async (input: PaymentsUser, action: string) => {
    const account = await accounts.getManagedBillingAccount(
      input.userId,
      input.organizationId,
    );
    if (account.mode !== "prepaid") {
      throw new BillingPaymentsError(
        "not_prepaid",
        `${action} are only available for prepaid organizations.`,
      );
    }

    return account;
  };

  // The card becomes the organization's saved card and the customer's default.
  // With `replacing`, a delayed event cannot overwrite a card saved since.
  const rememberCard = async (
    organizationId: string,
    card: SavedCard,
    replacing?: string | null,
  ) => {
    const saved = await accounts.savePaymentMethod({
      organizationId,
      stripeCustomerId: card.customerId,
      stripePaymentMethodId: card.paymentMethodId,
      ...(replacing === undefined ? {} : { replacing }),
    });
    if (!saved) {
      serviceLog("info", "stripe_card_superseded", {
        organization_id: organizationId,
      });
      return;
    }

    // Concurrent saves can reach Stripe out of order, so Stripe is pointed
    // again at whichever card is saved once each call returns.
    let paymentMethodId: string | null = card.paymentMethodId;
    for (
      let attempt = 0;
      paymentMethodId && attempt < CARD_SYNC_ATTEMPTS;
      attempt += 1
    ) {
      const target: string = paymentMethodId;
      await stripeCall("Stripe could not set the default card.", () =>
        gateway.setDefaultPaymentMethod(card.customerId, target),
      );
      paymentMethodId = await accounts.savedPaymentMethod(organizationId);
      if (paymentMethodId === target) return;
    }
  };

  const cacheCardDetails = (
    paymentMethodId: string,
    details: CardDetails | null,
  ) =>
    cardDetails
      .set(cardDetailsKey(paymentMethodId), JSON.stringify(details), {
        EX: details ? CARD_DETAILS_TTL_SECONDS : MISSING_CARD_TTL_SECONDS,
      })
      .catch(() => undefined);

  // Events can arrive out of order, so the customer's current default is read
  // from Stripe instead of trusting the event's payload.
  // Overlapping events can write in either order, so the default is read
  // again after each write until Stripe and the account agree.
  const followDefaultCard = async (
    customer: z.infer<typeof CustomerUpdatedEventSchema>["data"]["object"],
  ) => {
    const defaultCard = () =>
      stripeCall("Stripe could not return the card.", () =>
        gateway.retrieveDefaultCard(customer.id),
      );

    let card = await defaultCard();
    for (let attempt = 0; attempt < CARD_SYNC_ATTEMPTS; attempt += 1) {
      if (!card) {
        await accounts.clearCustomerPaymentMethod(customer.id);
      } else if (card.customerId === customer.id) {
        await accounts.updateCustomerPaymentMethod({
          stripeCustomerId: card.customerId,
          stripePaymentMethodId: card.paymentMethodId,
        });
      } else {
        return;
      }

      const written = card?.paymentMethodId ?? null;
      card = await defaultCard();
      if ((card?.paymentMethodId ?? null) === written) return;
    }
  };

  // Every Stripe flow uses the organization's one customer, created up front.
  const ensureCustomer = async (
    account: { stripeCustomerId: string | null },
    input: PaymentsUser,
  ): Promise<string> => {
    if (account.stripeCustomerId) return account.stripeCustomerId;

    const { customerId } = await stripeCall(
      "Stripe could not create the customer.",
      () =>
        gateway.createCustomer({
          organizationId: input.organizationId,
          email: input.userEmail,
        }),
    );

    return accounts.bindStripeCustomer(input.organizationId, customerId);
  };

  const creditPaidInvoice = async (
    invoice: z.infer<typeof TopUpChargeInvoiceEventSchema>["data"]["object"],
  ) => {
    if (invoice.currency !== "usd") {
      throw stripeEventRejection("top_up_charge", "currency");
    }

    await topUpCharges.succeed({
      chargeId: invoice.metadata.top_up_charge_id,
      stripeInvoiceId: invoice.id,
      amount: centsToNanoUsd(invoice.amount_paid),
    });
  };

  const chargeSavedCard = async (
    input: PaymentsUser & { amount: bigint; requestKey?: string },
  ): Promise<TopUpResult> => {
    const { charge, replayed } = await topUpCharges.claimTopUp({
      organizationId: input.organizationId,
      userId: input.userId,
      amount: input.amount,
      ...(input.requestKey ? { requestKey: input.requestKey } : {}),
    });
    // A retried request reports its first charge without charging again.
    if (replayed) {
      if (charge.status === "failed") {
        throw new BillingPaymentsError(
          "payment_failed",
          charge.failure ?? "The payment failed.",
        );
      }

      return cardResult(charge.status);
    }

    const fields = {
      organization_id: input.organizationId,
      user_id: input.userId,
    };

    let settled;
    try {
      settled = await settleTopUpCharge(
        { store: topUpCharges, charger, now: new Date() },
        charge,
      );
    } catch (error) {
      // The charge stays pending and the worker finishes it with the same keys.
      serviceLog("error", "top_up_charge_error", { ...fields, error });

      return cardResult("pending");
    }

    if (settled.status === "failed") {
      serviceLog("warn", "top_up_charge_failed", {
        ...fields,
        reason: `top_up:${settled.code}`,
      });
      throw new BillingPaymentsError("payment_failed", settled.failure);
    }

    serviceLog("info", `top_up_charge_${settled.status}`, fields);

    return cardResult(settled.status);
  };

  return {
    createTopUp: async ({ method, requestKey, ...input }) => {
      if (!isTopUpAmount(input.amount)) {
        throw new RangeError("The top-up amount is out of range.");
      }

      const account = await prepaidAccount(input, "Top-ups");
      const requested =
        method === "checkout" || !account.stripePaymentMethodId
          ? "checkout"
          : "card";
      // A retry repeats its first attempt, even if it asks for another method
      // or the saved card has changed, so one request cannot pay twice.
      const first = requestKey
        ? await topUpCharges.recordRequest({
            organizationId: input.organizationId,
            requestKey,
            method: requested,
            amount: input.amount,
            requestedBy: input.userId,
            replacesPaymentMethodId: account.stripePaymentMethodId,
          })
        : null;
      if (first && first.amount !== input.amount) {
        throw new ControlServiceError(
          "conflict",
          "This idempotency key was used for a different amount.",
        );
      }

      // Stripe forgets Checkout idempotency keys after a day, so an older key
      // could open a second payable session.
      if (
        first?.method === "checkout" &&
        Date.now() - first.createdAt.getTime() > CHECKOUT_REQUEST_LIFETIME_MS
      ) {
        throw new ControlServiceError(
          "conflict",
          "This idempotency key has expired. Use a new one.",
        );
      }

      if ((first?.method ?? requested) === "card") {
        return chargeSavedCard({
          ...input,
          ...(requestKey ? { requestKey } : {}),
        });
      }

      const customerId = await ensureCustomer(account, input);
      const { url } = await stripeCall("Stripe could not start Checkout.", () =>
        gateway.createCheckoutSession({
          amountCents: nanoUsdToCents(input.amount),
          organizationId: input.organizationId,
          // A retry resends the first request's parameters, as Stripe
          // rejects a reused key with different ones.
          userId: first?.requestedBy ?? input.userId,
          customerId,
          replacesPaymentMethodId: first
            ? first.replacesPaymentMethodId
            : account.stripePaymentMethodId,
          ...(requestKey ? { requestKey } : {}),
          successUrl: `${baseProductUrl}/billing?topup=success&session_id={CHECKOUT_SESSION_ID}`,
          cancelUrl: `${baseProductUrl}/billing?topup=cancelled`,
        }),
      );
      if (!url) {
        throw new BillingPaymentsError(
          "provider_error",
          "Stripe did not return a Checkout URL.",
        );
      }

      return { status: "checkout", checkoutUrl: url };
    },

    // The billing portal lists invoices and billing details; cards change in the console.
    createPaymentMethodSession: async (input) => {
      const account = await prepaidAccount(input, "Billing history");
      const customerId = account.stripeCustomerId;
      if (!customerId) {
        throw new BillingPaymentsError(
          "no_billing_customer",
          "Billing history is available after your first payment or saved card.",
        );
      }

      return stripeCall("Stripe could not open the billing portal.", () =>
        gateway.createBillingPortalSession({
          customerId,
          returnUrl: `${baseProductUrl}/billing`,
        }),
      );
    },

    createCardSetup: async (input) => {
      const account = await prepaidAccount(input, "Saved cards");
      if (!publishableKey) {
        throw new BillingPaymentsError(
          "unavailable",
          "Card entry is not configured.",
        );
      }

      const customerId = await ensureCustomer(account, input);
      const { clientSecret } = await stripeCall(
        "Stripe could not start card entry.",
        () =>
          gateway.createCardSetup({
            organizationId: input.organizationId,
            userId: input.userId,
            customerId,
            replacesPaymentMethodId: account.stripePaymentMethodId,
          }),
      );

      return { clientSecret, publishableKey };
    },

    describeCard: async (paymentMethodId) => {
      const cached = await cardDetails
        .get(cardDetailsKey(paymentMethodId))
        .catch(() => null);
      if (cached) return JSON.parse(cached) as CardDetails | null;

      try {
        const card = await gateway.retrieveCard(paymentMethodId);
        const details = card && cardDetailsOf(card);
        await cacheCardDetails(paymentMethodId, details);

        return details;
      } catch (error) {
        serviceLog("warn", "stripe_card_details_unavailable", { error });
        // A short negative entry keeps polling pages from piling onto Stripe.
        await cacheCardDetails(paymentMethodId, null);

        return null;
      }
    },

    saveCard: async (input) => {
      await prepaidAccount(input, "Saved cards");
      const setup = await stripeCall("Stripe could not return the card.", () =>
        gateway.retrieveCardSetup(input.setupIntentId),
      );

      // The SetupIntent must be this organization's and confirmed with a card.
      if (setup.organizationId !== input.organizationId || !setup.card) {
        throw new BillingPaymentsError(
          "card_not_confirmed",
          "The card was not confirmed. Enter it again.",
        );
      }

      // A delayed save cannot replace a card saved after setup began.
      await rememberCard(
        input.organizationId,
        setup.card,
        setup.replacesPaymentMethodId,
      );
      await cacheCardDetails(
        setup.card.paymentMethodId,
        cardDetailsOf(setup.card),
      );
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

      const customer = CustomerUpdatedEventSchema.safeParse(event);
      if (customer.success) return followDefaultCard(customer.data.data.object);

      const invoice = TopUpChargeInvoiceEventSchema.safeParse(event);
      if (invoice.success) return creditPaidInvoice(invoice.data.data.object);

      // Only a pending charge is failed, so this never undoes a paid one.
      const failedInvoice =
        TopUpChargeInvoiceFailedEventSchema.safeParse(event);
      if (failedInvoice.success) {
        return topUpCharges.fail({
          chargeId: failedInvoice.data.data.object.metadata.top_up_charge_id,
          failure: "The payment failed.",
        });
      }

      if (!TopUpEventSchema.safeParse(event).success) return;

      const parsed = StripeCheckoutEventSchema.safeParse(event);
      if (!parsed.success)
        throw stripeEventRejection("topup", "schema", parsed.error);

      const session = parsed.data.data.object;
      if (session.payment_status !== "paid") return;

      const metadata = TopUpMetadataSchema.safeParse(session.metadata);
      if (
        !metadata.success ||
        session.client_reference_id !== metadata.data.organization_id
      ) {
        throw stripeEventRejection(
          "topup",
          "metadata_mismatch",
          metadata.error,
        );
      }

      if (session.currency !== "usd")
        throw stripeEventRejection("topup", "currency");

      const amount =
        session.amount_total === null
          ? null
          : centsToNanoUsd(session.amount_total);
      if (amount === null || !isTopUpAmount(amount)) {
        throw stripeEventRejection("topup", "amount_out_of_range");
      }

      const customerId = stripeId(session.customer);

      await accounts.applyBalanceTransaction({
        organizationId: metadata.data.organization_id,
        type: "topup",
        amount,
        sourceType: "stripe_checkout_session",
        sourceId: session.id,
        createdBy: metadata.data.user_id,
        stripeCustomerId: customerId,
      });

      // The card paid with becomes the saved card; the credit above is
      // idempotent, so a failure here lets Stripe retry the whole event.
      const paymentIntentId = stripeId(session.payment_intent ?? null);
      if (!paymentIntentId) return;

      const card = await stripeCall("Stripe could not return the card.", () =>
        gateway.retrievePaymentCard(paymentIntentId),
      );
      if (card) {
        await rememberCard(
          metadata.data.organization_id,
          card,
          metadata.data.replaces_payment_method || null,
        );
      }
    },
  };
};

const unavailable = (detail: string) => async (): Promise<never> => {
  throw new BillingPaymentsError("unavailable", detail);
};

export const unavailableBillingPaymentsService =
  (): BillingPaymentsService => ({
    createTopUp: unavailable("Stripe Checkout is not configured."),
    createPaymentMethodSession: unavailable(
      "Stripe Checkout is not configured.",
    ),
    createCardSetup: unavailable("Card entry is not configured."),
    saveCard: unavailable("Card entry is not configured."),
    describeCard: async () => null,
    handleWebhook: unavailable("Stripe webhooks are not configured."),
  });
