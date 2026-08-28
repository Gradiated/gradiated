import {
  BalanceTransactionListSchema,
  BillingAccountSchema,
  CreateTopUpCheckoutSchema,
  ModelListSchema,
  OrganizationIdParamsSchema,
  StripeWebhookHeadersSchema,
  StripeWebhookPayloadSchema,
  StripeWebhookResponseSchema,
  TopUpCheckoutSchema,
  problemContent,
  type BalanceTransaction,
  type BillingAccount,
  type Model,
} from "@gradiated/contracts";
import {
  ControlServiceError,
  type BalanceTransactionRecord,
  type BillingAccountRecord,
  type ModelRecord,
} from "@gradiated/control";
import { createRoute, type OpenAPIHono } from "@hono/zod-openapi";

import { BillingPaymentsError } from "../billing/stripe.js";
import { problemDocument } from "../http/problem-response.js";
import type { ApiEnvironment, ApiServices } from "../types.js";

const listModelsRoute = createRoute({
  method: "get",
  path: "/api/v1/models",
  operationId: "listModels",
  tags: ["Models"],
  responses: {
    200: {
      description: "The public catalog of supported exact models and prices.",
      content: { "application/json": { schema: ModelListSchema } },
    },
  },
});

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
  request: { params: OrganizationIdParamsSchema },
  responses: {
    200: {
      description: "The organization's latest durable balance movements.",
      content: { "application/json": { schema: BalanceTransactionListSchema } },
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

const modelResponse = (record: ModelRecord): Model => {
  if (record.status === "retired") {
    throw new Error("Retired models cannot be returned by the catalog.");
  }
  return {
    id: record.id,
    name: record.name,
    status: record.status,
    properties: record.properties,
    created_at: record.createdAt.toISOString(),
    updated_at: record.updatedAt.toISOString(),
  };
};

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

const unauthenticated = (context: Parameters<typeof problemDocument>[0]) =>
  context.json(
    problemDocument(context, {
      type: "https://gradiated.com/problems/unauthenticated",
      title: "Authentication required",
      status: 401,
      detail: "A valid human session is required for this operation.",
      code: "unauthenticated",
    }),
    401,
    { "Content-Type": "application/problem+json" },
  );

const catalogBillingError = (
  context: Parameters<typeof problemDocument>[0],
  error: unknown,
) => {
  if (!(error instanceof ControlServiceError)) throw error;
  const status = error.code === "forbidden" ? 403 : 404;
  return context.json(
    problemDocument(context, {
      type: `https://gradiated.com/problems/${error.code === "forbidden" ? "forbidden" : "not-found"}`,
      title: error.code === "forbidden" ? "Forbidden" : "Not found",
      status,
      detail: error.message,
      code: error.code,
    }),
    status,
    { "Content-Type": "application/problem+json" },
  );
};

const checkoutPaymentsError = (
  context: Parameters<typeof problemDocument>[0],
  error: unknown,
) => {
  if (!(error instanceof BillingPaymentsError)) throw error;
  if (error.code === "not_prepaid") {
    return context.json(
      problemDocument(context, {
        type: "https://gradiated.com/problems/not-prepaid",
        title: "Prepaid billing required",
        status: 409,
        detail: error.message,
        code: error.code,
      }),
      409,
      { "Content-Type": "application/problem+json" },
    );
  }
  return context.json(
    problemDocument(context, {
      type: "https://gradiated.com/problems/billing-provider-unavailable",
      title: "Billing provider unavailable",
      status: 503,
      detail: error.message,
      code: error.code,
    }),
    503,
    { "Content-Type": "application/problem+json" },
  );
};

const webhookPaymentsError = (
  context: Parameters<typeof problemDocument>[0],
  error: unknown,
) => {
  if (!(error instanceof BillingPaymentsError)) throw error;
  if (error.code === "invalid_webhook") {
    return context.json(
      problemDocument(context, {
        type: "https://gradiated.com/problems/invalid-stripe-webhook",
        title: "Invalid Stripe webhook",
        status: 400,
        detail: error.message,
        code: error.code,
      }),
      400,
      { "Content-Type": "application/problem+json" },
    );
  }
  return context.json(
    problemDocument(context, {
      type: "https://gradiated.com/problems/billing-provider-unavailable",
      title: "Billing provider unavailable",
      status: 503,
      detail: error.message,
      code: error.code,
    }),
    503,
    { "Content-Type": "application/problem+json" },
  );
};

export const registerCatalogBillingRoutes = (
  app: OpenAPIHono<ApiEnvironment>,
  services: ApiServices,
): void => {
  app.openapi(listModelsRoute, async (context) => {
    const records = await services.catalogBilling.listModels();
    return context.json(
      { data: records.map(modelResponse), next_cursor: null },
      200,
    );
  });

  app.openapi(getBillingAccountRoute, async (context) => {
    const user = context.get("user");
    if (!user) return unauthenticated(context);
    try {
      const record = await services.catalogBilling.getBillingAccount(
        user.id,
        context.req.valid("param").organization_id,
      );
      return context.json(billingAccountResponse(record), 200);
    } catch (error) {
      return catalogBillingError(context, error);
    }
  });

  app.openapi(listBalanceTransactionsRoute, async (context) => {
    const user = context.get("user");
    if (!user) return unauthenticated(context);
    try {
      const records = await services.catalogBilling.listBalanceTransactions(
        user.id,
        context.req.valid("param").organization_id,
      );
      return context.json(
        { data: records.map(balanceTransactionResponse), next_cursor: null },
        200,
      );
    } catch (error) {
      return catalogBillingError(context, error);
    }
  });

  app.openapi(createTopUpCheckoutRoute, async (context) => {
    const user = context.get("user");
    if (!user) return unauthenticated(context);
    try {
      const checkout = await services.billingPayments.createTopUpCheckout({
        userId: user.id,
        userEmail: user.email,
        organizationId: context.req.valid("param").organization_id,
        amount: BigInt(context.req.valid("json").amount),
      });
      return context.json({ checkout_url: checkout.checkoutUrl }, 201);
    } catch (error) {
      if (error instanceof ControlServiceError) {
        return catalogBillingError(context, error);
      }
      return checkoutPaymentsError(context, error);
    }
  });

  app.openapi(stripeWebhookRoute, async (context) => {
    try {
      await services.billingPayments.handleWebhook({
        payload: await context.req.text(),
        signature: context.req.valid("header")["stripe-signature"],
      });
      return context.json({ received: true as const }, 200);
    } catch (error) {
      return webhookPaymentsError(context, error);
    }
  });
};
