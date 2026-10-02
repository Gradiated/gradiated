import {
  BalanceTransactionListSchema,
  BalanceTransactionQuerySchema,
  BillingAccountSchema,
  CreateTopUpCheckoutSchema,
  OrganizationIdParamsSchema,
  StripeWebhookHeadersSchema,
  StripeWebhookPayloadSchema,
  StripeWebhookResponseSchema,
  TopUpCheckoutSchema,
  problemContent,
  type BalanceTransaction,
  type BillingAccount,
} from "@gradiated/contracts";
import type {
  BalanceTransactionRecord,
  BillingAccountRecord,
  CatalogBillingService,
} from "@gradiated/control";
import { createRoute, type OpenAPIHono } from "@hono/zod-openapi";

import type { BillingPaymentsService } from "../billing/top-ups.js";
import { requireUser } from "../http/problems.js";
import type { ApiEnvironment } from "../types.js";

const getBillingAccountRoute = createRoute({
  method: "get",
  path: "/api/v1/organizations/{organization_id}/billing",
  operationId: "getBillingAccount",
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

const listBalanceTransactionsRoute = createRoute({
  method: "get",
  path: "/api/v1/organizations/{organization_id}/balance-transactions",
  operationId: "listBalanceTransactions",
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

const createTopUpCheckoutRoute = createRoute({
  method: "post",
  path: "/api/v1/organizations/{organization_id}/billing/top-ups",
  operationId: "createTopUpCheckout",
  tags: ["Billing"],
  request: {
    params: OrganizationIdParamsSchema,
    body: {
      required: true,
      content: { "application/json": { schema: CreateTopUpCheckoutSchema } },
    },
  },
  responses: {
    201: {
      description: "A Stripe-hosted Checkout Session for this top-up.",
      content: { "application/json": { schema: TopUpCheckoutSchema } },
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
): BillingAccount => ({
  organization_id: record.organizationId,
  mode: record.mode,
  balance: record.balance.toString(),
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
      "getBillingAccount" | "listBalanceTransactions"
    >;
    payments: BillingPaymentsService;
  },
): void => {
  app.openapi(getBillingAccountRoute, async (context) => {
    const user = await requireUser(context);
    const record = await accounts.getBillingAccount(
      user.id,
      context.req.valid("param").organization_id,
    );

    return context.json(billingAccountResponse(record), 200);
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

  app.openapi(createTopUpCheckoutRoute, async (context) => {
    const user = await requireUser(context);
    const checkout = await payments.createTopUpCheckout({
      userId: user.id,
      userEmail: user.email,
      organizationId: context.req.valid("param").organization_id,
      amount: BigInt(context.req.valid("json").amount),
    });

    return context.json({ checkout_url: checkout.checkoutUrl }, 201);
  });

  app.openapi(stripeWebhookRoute, async (context) => {
    await payments.handleWebhook({
      payload: await context.req.text(),
      signature: context.req.valid("header")["stripe-signature"],
    });

    return context.json({ received: true as const }, 200);
  });
};
