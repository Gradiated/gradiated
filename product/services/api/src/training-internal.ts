import { createHash, timingSafeEqual } from "node:crypto";

import {
  BalanceCheckResultSchema,
  BalanceCheckSchema,
  PriceListQuerySchema,
  PriceListSchema,
  UsageEventBatchSchema,
  UsageEventIngestResultSchema,
  UsageEventRejectionSchema,
  problemContent,
} from "@gradiated/contracts";
import {
  UsageEventRejectedError,
  type PriceListRecord,
  type TrainingBillingService,
} from "@gradiated/control";
import { createRoute, OpenAPIHono } from "@hono/zod-openapi";
import { bodyLimit } from "hono/body-limit";
import { requestId } from "hono/request-id";

import { problemResponse, problems, toApiProblem } from "./http/problems.js";
import { serviceLog } from "./logging.js";
import type { ApiEnvironment } from "./types.js";

export interface TrainingInternalDependencies {
  // The current token and, during a rotation, the previous one.
  tokens: readonly string[];
  billing: TrainingBillingService;
}

const digest = (value: string) => createHash("sha256").update(value).digest();

// Comparing fixed-length digests hides both the token and its length.
export const createTokenCheck = (tokens: readonly string[]) => {
  const expected = tokens.map(digest);

  return (authorization: string | undefined): boolean => {
    const match = authorization?.match(/^Bearer (\S+)$/);
    if (!match?.[1]) return false;

    const supplied = digest(match[1]);

    return expected.reduce(
      (matched, candidate) => timingSafeEqual(supplied, candidate) || matched,
      false,
    );
  };
};

const unauthorized = {
  401: {
    description: "The service token is missing or wrong.",
    content: problemContent,
  },
};

const pricesRoute = createRoute({
  method: "get",
  path: "/api/internal/v1/billing/prices",
  operationId: "getTrainingPriceList",
  summary: "Get the training price list",
  description:
    "The price-list version in effect, or the named one. Versions are immutable; the ETag is the version, so If-None-Match returns 304 until it changes.",
  tags: ["Training billing"],
  request: { query: PriceListQuerySchema },
  responses: {
    200: {
      description: "The price list.",
      headers: { ETag: { schema: { type: "string" } } },
      content: { "application/json": { schema: PriceListSchema } },
    },
    304: { description: "The caller has this version." },
    ...unauthorized,
    404: { description: "No such version.", content: problemContent },
  },
});

const checkRoute = createRoute({
  method: "post",
  path: "/api/internal/v1/billing/check",
  operationId: "checkTrainingBalance",
  summary: "Check a workspace's balance",
  description:
    "Whether the workspace's organization can pay for the estimate: invoiced organizations always can, prepaid ones while the balance covers it. Suspended organizations and archived workspaces cannot.",
  tags: ["Training billing"],
  request: {
    body: {
      required: true,
      content: { "application/json": { schema: BalanceCheckSchema } },
    },
  },
  responses: {
    200: {
      description: "The decision.",
      content: { "application/json": { schema: BalanceCheckResultSchema } },
    },
    ...unauthorized,
    404: {
      description: "The workspace does not exist.",
      content: problemContent,
    },
  },
});

const usageEventsRoute = createRoute({
  method: "post",
  path: "/api/internal/v1/billing/usage-events",
  operationId: "ingestTrainingUsageEvents",
  summary: "Ingest training usage",
  description:
    "Bills up to 500 priced usage events in one transaction. Replays of an event ID are free and counted as duplicates. Nothing in a batch is billed when one event is rejected.",
  tags: ["Training billing"],
  request: {
    body: {
      required: true,
      content: { "application/json": { schema: UsageEventBatchSchema } },
    },
  },
  responses: {
    200: {
      description: "The batch was billed.",
      content: { "application/json": { schema: UsageEventIngestResultSchema } },
    },
    ...unauthorized,
    409: {
      description: "An event ID was already billed with different values.",
      content: { "application/json": { schema: UsageEventRejectionSchema } },
    },
    422: {
      description:
        "An event's price does not match its version, or its workspace is unknown.",
      content: { "application/json": { schema: UsageEventRejectionSchema } },
    },
  },
});

const priceListResponse = (list: PriceListRecord) => ({
  price_version: list.id,
  product: list.product,
  effective_at: list.effectiveAt.toISOString(),
  placeholder: list.placeholder,
  skus: list.items.map((item) => ({
    sku: item.sku,
    unit: item.unit,
    price_nano_usd_per_mtok: Number(item.priceNanoUsdPerMillion),
  })),
});

const etagOf = (version: string) => `"${version}"`;

export const createTrainingInternalApp = ({
  tokens,
  billing,
}: TrainingInternalDependencies) => {
  const authorized = createTokenCheck(tokens);
  const app = new OpenAPIHono<ApiEnvironment>({
    defaultHook: (result, context) => {
      if (result.success) return;

      return problemResponse(
        context,
        problems.validation(
          result.error.issues.map((issue) => ({
            path: issue.path.join("."),
            message: issue.message,
          })),
        ),
      );
    },
  });

  app.use("*", requestId());
  app.get("/health/live", (context) => context.text("ok\n"));
  app.use("/api/internal/*", async (context, next) => {
    if (!authorized(context.req.header("authorization")))
      return problemResponse(context, problems.unauthenticated);

    await next();
  });
  app.use(
    "/api/internal/*",
    bodyLimit({
      maxSize: 2 * 1024 * 1024,
      onError: (context) => problemResponse(context, problems.payloadTooLarge),
    }),
  );

  app.openapi(pricesRoute, async (context) => {
    const query = context.req.valid("query");
    const list = await billing.priceList({
      product: query.product,
      priceVersion: query.price_version,
    });

    const etag = etagOf(list.id);
    context.header("ETag", etag);
    context.header("Cache-Control", "no-cache");
    if (context.req.header("if-none-match") === etag)
      return context.body(null, 304);

    return context.json(priceListResponse(list), 200);
  });

  app.openapi(checkRoute, async (context) =>
    context.json(await billing.checkBalance(context.req.valid("json")), 200),
  );

  app.openapi(usageEventsRoute, async (context) => {
    try {
      const result = await billing.ingestUsageEvents(
        context.req.valid("json").events,
      );

      return context.json(result, 200);
    } catch (error) {
      if (!(error instanceof UsageEventRejectedError)) throw error;

      serviceLog("error", "training_usage_rejected", { reason: error.code });
      return context.json(
        { code: error.code, event_id: error.eventId, message: error.message },
        error.code === "event_conflict" ? 409 : 422,
      );
    }
  });

  app.onError((error, context) => {
    const problem = toApiProblem(error);
    if (!problem || problem.problem.status >= 500)
      serviceLog("error", "training_internal_failed", {
        error: problem?.cause ?? error,
        route: context.req.routePath,
      });

    return problemResponse(context, problem?.problem ?? problems.internal);
  });

  return app;
};
