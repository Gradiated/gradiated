import {
  BalanceTransactionListSchema,
  BalanceTransactionQuerySchema,
  BillingAccountSchema,
  CardSetupSchema,
  CreateTopUpSchema,
  OrganizationIdParamsSchema,
  PaymentMethodSessionSchema,
  SaveCardSchema,
  StripeWebhookHeadersSchema,
  StripeWebhookPayloadSchema,
  StripeWebhookResponseSchema,
  TopUpSchema,
  UpdateBillingAccountSchema,
  problemContent,
  type BalanceTransaction,
  type BillingAccount,
} from "@gradiated/contracts";
import type {
  BalanceTransactionRecord,
  BillingAccountRecord,
  CatalogBillingService,
  TopUpStatus,
} from "@gradiated/control";
import { createRoute, type OpenAPIHono } from "@hono/zod-openapi";

import type {
  BillingPaymentsService,
  CardDetails,
} from "../billing/payments.js";
import { requireUser } from "../http/problems.js";
import { consoleOnly } from "../http/audience.js";
import type { ApiEnvironment } from "../types.js";

const getBillingAccountRoute = createRoute({
  method: "get",
  path: "/api/v1/organizations/{organization_id}/billing",
  operationId: "getBillingAccount",
  summary: "Get billing account",
  description: "Gets the organization's balance and auto top-up settings.",
  tags: ["Billing"],
  request: { params: OrganizationIdParamsSchema },
  responses: {
    200: {
      description: "The organization's durable posted billing balance.",
      content: { "application/json": { schema: BillingAccountSchema } },
    },
    401: {
      description: "Authentication is required.",
      content: problemContent,
    },
    403: {
      description: "The caller cannot view billing.",
      content: problemContent,
    },
    404: {
      description: "The billing account was not found.",
      content: problemContent,
    },
  },
});

const updateBillingAccountRoute = createRoute({
  method: "patch",
  path: "/api/v1/organizations/{organization_id}/billing",
  operationId: "updateBillingAccount",
  summary: "Update billing account",
  description: "Changes the organization's auto top-up settings.",
  tags: ["Billing"],
  request: {
    params: OrganizationIdParamsSchema,
    body: {
      required: true,
      content: { "application/json": { schema: UpdateBillingAccountSchema } },
    },
  },
  responses: {
    200: {
      description: "The billing account with its new auto top-up settings.",
      content: { "application/json": { schema: BillingAccountSchema } },
    },
    401: {
      description: "Authentication is required.",
      content: problemContent,
    },
    403: {
      description: "The caller cannot manage billing.",
      content: problemContent,
    },
    404: {
      description: "The billing account was not found.",
      content: problemContent,
    },
    409: {
      description:
        "The organization is not prepaid, or auto top-up was turned on without a saved card.",
      content: problemContent,
    },
    422: {
      description: "The auto top-up settings are invalid.",
      content: problemContent,
    },
  },
});

const createPaymentMethodSessionRoute = createRoute({
  ...consoleOnly,
  method: "post",
  path: "/api/v1/organizations/{organization_id}/billing/payment-method-sessions",
  operationId: "createPaymentMethodSession",
  summary: "Create billing portal session",
  description:
    "Opens the Stripe billing portal for invoices, receipts and billing details.",
  tags: ["Billing"],
  request: { params: OrganizationIdParamsSchema },
  responses: {
    201: {
      description: "The Stripe billing portal for the organization.",
      content: { "application/json": { schema: PaymentMethodSessionSchema } },
    },
    401: {
      description: "Authentication is required.",
      content: problemContent,
    },
    403: {
      description: "The caller cannot manage billing.",
      content: problemContent,
    },
    404: {
      description: "The organization was not found.",
      content: problemContent,
    },
    409: {
      description:
        "The organization does not use prepaid billing or has no billing history yet.",
      content: problemContent,
    },
    503: {
      description: "Stripe is unavailable.",
      content: problemContent,
    },
  },
});

const createCardSetupRoute = createRoute({
  ...consoleOnly,
  method: "post",
  path: "/api/v1/organizations/{organization_id}/billing/card-setups",
  operationId: "createCardSetup",
  summary: "Start card entry",
  description:
    "Creates a card-only Stripe SetupIntent for entering a card in the console.",
  tags: ["Billing"],
  request: { params: OrganizationIdParamsSchema },
  responses: {
    201: {
      description: "The SetupIntent client secret and Stripe publishable key.",
      content: { "application/json": { schema: CardSetupSchema } },
    },
    401: {
      description: "Authentication is required.",
      content: problemContent,
    },
    403: {
      description: "The caller cannot manage billing.",
      content: problemContent,
    },
    404: {
      description: "The organization was not found.",
      content: problemContent,
    },
    409: {
      description: "The organization does not use prepaid billing.",
      content: problemContent,
    },
    503: {
      description: "Stripe or card entry is unavailable.",
      content: problemContent,
    },
  },
});

const saveCardRoute = createRoute({
  ...consoleOnly,
  method: "post",
  path: "/api/v1/organizations/{organization_id}/billing/card",
  operationId: "saveCard",
  summary: "Save card",
  description:
    "Saves the card from a confirmed SetupIntent as the organization's card for top-ups and auto top-up.",
  tags: ["Billing"],
  request: {
    params: OrganizationIdParamsSchema,
    body: {
      required: true,
      content: { "application/json": { schema: SaveCardSchema } },
    },
  },
  responses: {
    200: {
      description: "The billing account with the saved card.",
      content: { "application/json": { schema: BillingAccountSchema } },
    },
    401: {
      description: "Authentication is required.",
      content: problemContent,
    },
    403: {
      description: "The caller cannot manage billing.",
      content: problemContent,
    },
    404: {
      description: "The organization was not found.",
      content: problemContent,
    },
    409: {
      description:
        "The SetupIntent was not confirmed for this organization, or billing is not prepaid.",
      content: problemContent,
    },
    503: {
      description: "Stripe or card entry is unavailable.",
      content: problemContent,
    },
  },
});

const listBalanceTransactionsRoute = createRoute({
  method: "get",
  path: "/api/v1/organizations/{organization_id}/balance-transactions",
  operationId: "listBalanceTransactions",
  summary: "List balance transactions",
  description: "Lists changes to the organization's balance.",
  tags: ["Billing"],
  request: {
    params: OrganizationIdParamsSchema,
    query: BalanceTransactionQuerySchema,
  },
  responses: {
    200: {
      description:
        "The organization's durable balance movements, newest first.",
      content: { "application/json": { schema: BalanceTransactionListSchema } },
    },
    422: {
      description: "The pagination parameters are invalid.",
      content: problemContent,
    },
    401: {
      description: "Authentication is required.",
      content: problemContent,
    },
    403: {
      description: "The caller cannot view billing.",
      content: problemContent,
    },
    404: {
      description: "The organization was not found.",
      content: problemContent,
    },
  },
});

const createTopUpRoute = createRoute({
  ...consoleOnly,
  method: "post",
  path: "/api/v1/organizations/{organization_id}/billing/top-ups",
  operationId: "createTopUp",
  summary: "Create top-up",
  description:
    "Adds funds by charging the saved card, or through Stripe Checkout.",
  tags: ["Billing"],
  request: {
    params: OrganizationIdParamsSchema,
    body: {
      required: true,
      content: { "application/json": { schema: CreateTopUpSchema } },
    },
  },
  responses: {
    201: {
      description: "The card was charged, or Checkout is ready to pay.",
      content: { "application/json": { schema: TopUpSchema } },
    },
    402: {
      description: "The saved card was declined.",
      content: problemContent,
    },
    401: {
      description: "Authentication is required.",
      content: problemContent,
    },
    403: {
      description: "The caller cannot manage billing.",
      content: problemContent,
    },
    404: {
      description: "The organization was not found.",
      content: problemContent,
    },
    409: {
      description:
        "The organization does not use prepaid billing, or another payment is in progress.",
      content: problemContent,
    },
    503: {
      description: "Stripe Checkout is unavailable.",
      content: problemContent,
    },
  },
});

const stripeWebhookRoute = createRoute({
  hide: true,
  method: "post",
  path: "/api/webhooks/stripe",
  operationId: "handleStripeWebhook",
  tags: ["Billing"],
  request: {
    headers: StripeWebhookHeadersSchema,
    body: {
      required: true,
      content: { "application/json": { schema: StripeWebhookPayloadSchema } },
    },
  },
  responses: {
    200: {
      description: "The signed Stripe event was accepted.",
      content: { "application/json": { schema: StripeWebhookResponseSchema } },
    },
    400: {
      description: "The signature or event payload is invalid.",
      content: problemContent,
    },
    503: {
      description: "Stripe webhooks are not configured.",
      content: problemContent,
    },
  },
});

const billingAccountResponse = (
  record: BillingAccountRecord,
  card: CardDetails | null,
  status: TopUpStatus,
): BillingAccount => ({
  organization_id: record.organizationId,
  mode: record.mode,
  balance: record.balance.toString(),
  payment_method: record.stripePaymentMethodId
    ? {
        brand: card?.brand ?? null,
        last4: card?.last4 ?? null,
        exp_month: card?.expMonth ?? null,
        exp_year: card?.expYear ?? null,
      }
    : null,
  auto_top_up: {
    enabled: record.autoTopUpEnabled,
    threshold: record.autoTopUpThreshold?.toString() ?? null,
    amount: record.autoTopUpAmount?.toString() ?? null,
    // The reason shows only while auto top-up is off.
    failure: record.autoTopUpEnabled ? null : status.autoTopUpFailure,
  },
  top_up_pending: status.pending,
  billing_portal: record.stripeCustomerId !== null,
  created_at: record.createdAt.toISOString(),
  updated_at: record.updatedAt.toISOString(),
});

const balanceTransactionResponse = (
  record: BalanceTransactionRecord,
): BalanceTransaction => ({
  id: record.id,
  organization_id: record.organizationId,
  type: record.type,
  amount: record.amount.toString(),
  balance_after: record.balanceAfter.toString(),
  source_type: record.sourceType,
  stripe_id: record.sourceType.startsWith("stripe_") ? record.sourceId : null,
  period_start: record.periodStart?.toISOString() ?? null,
  period_end: record.periodEnd?.toISOString() ?? null,
  generation_count: record.generationCount?.toString() ?? null,
  created_at: record.createdAt.toISOString(),
});

export const registerBillingRoutes = (
  app: OpenAPIHono<ApiEnvironment>,
  {
    accounts,
    payments,
  }: {
    accounts: Pick<
      CatalogBillingService,
      | "getBillingAccount"
      | "listBalanceTransactions"
      | "updateAutoTopUp"
      | "topUpStatus"
    >;
    payments: BillingPaymentsService;
  },
): void => {
  // Card details come from Stripe; charge state comes from the charge store.
  const account = async (record: BillingAccountRecord) => {
    const [card, status] = await Promise.all([
      record.stripePaymentMethodId
        ? payments.describeCard(record.stripePaymentMethodId)
        : null,
      accounts.topUpStatus(record.organizationId),
    ]);

    return billingAccountResponse(record, card, status);
  };

  app.openapi(getBillingAccountRoute, async (context) => {
    const user = await requireUser(context);
    const record = await accounts.getBillingAccount(
      user.id,
      context.req.valid("param").organization_id,
    );

    return context.json(await account(record), 200);
  });

  app.openapi(updateBillingAccountRoute, async (context) => {
    const user = await requireUser(context);
    const record = await accounts.updateAutoTopUp(
      user.id,
      context.req.valid("param").organization_id,
      context.req.valid("json").auto_top_up,
    );

    return context.json(await account(record), 200);
  });

  app.openapi(createPaymentMethodSessionRoute, async (context) => {
    const user = await requireUser(context);
    const session = await payments.createPaymentMethodSession({
      userId: user.id,
      userEmail: user.email,
      organizationId: context.req.valid("param").organization_id,
    });

    return context.json({ url: session.url }, 201);
  });

  app.openapi(createCardSetupRoute, async (context) => {
    const user = await requireUser(context);
    const setup = await payments.createCardSetup({
      userId: user.id,
      userEmail: user.email,
      organizationId: context.req.valid("param").organization_id,
    });

    return context.json(
      {
        client_secret: setup.clientSecret,
        publishable_key: setup.publishableKey,
      },
      201,
    );
  });

  app.openapi(saveCardRoute, async (context) => {
    const user = await requireUser(context);
    const organizationId = context.req.valid("param").organization_id;
    await payments.saveCard({
      userId: user.id,
      userEmail: user.email,
      organizationId,
      setupIntentId: context.req.valid("json").setup_intent_id,
    });
    const record = await accounts.getBillingAccount(user.id, organizationId);

    return context.json(await account(record), 200);
  });

  app.openapi(listBalanceTransactionsRoute, async (context) => {
    const user = await requireUser(context);
    const page = await accounts.listBalanceTransactions(
      user.id,
      context.req.valid("param").organization_id,
      context.req.valid("query"),
    );

    return context.json(
      {
        data: page.data.map(balanceTransactionResponse),
        next_cursor: page.nextCursor,
      },
      200,
    );
  });

  app.openapi(createTopUpRoute, async (context) => {
    const user = await requireUser(context);
    const organizationId = context.req.valid("param").organization_id;
    const {
      amount,
      method,
      idempotency_key: idempotencyKey,
    } = context.req.valid("json");
    const topUp = await payments.createTopUp({
      userId: user.id,
      userEmail: user.email,
      organizationId,
      amount: BigInt(amount),
      ...(method ? { method } : {}),
      ...(idempotencyKey ? { requestKey: idempotencyKey } : {}),
    });

    if (topUp.status === "checkout") {
      context.get("analytics")?.track(user.id, "billing_checkout_started", {
        organization_id: organizationId,
        amount_nano_usd: amount,
        currency: "USD",
      });
    }

    return context.json(
      { status: topUp.status, checkout_url: topUp.checkoutUrl },
      201,
    );
  });

  app.openapi(stripeWebhookRoute, async (context) => {
    await payments.handleWebhook({
      payload: await context.req.text(),
      signature: context.req.valid("header")["stripe-signature"],
    });

    return context.json({ received: true as const }, 200);
  });
};
