import { rateLimiter } from "hono-rate-limiter";

import type { ApiEnvironment } from "../types.js";
import { problemResponse, problems } from "./problems.js";

export const apiRateLimit = (limit = 300) =>
  rateLimiter<ApiEnvironment>({
    windowMs: 60_000,
    limit,
    standardHeaders: "draft-6",
    // Stripe retries have their own signed webhook path and must not share a client quota.
    skip: (context) => context.req.path === "/api/webhooks/stripe",
    keyGenerator: (context) =>
      // The production ALB appends the real client IP after any supplied addresses.
      context.req.header("x-forwarded-for")?.split(",").at(-1)?.trim() ||
      context.env?.incoming?.socket?.remoteAddress ||
      "unknown",
    handler: (context) => problemResponse(context, problems.tooManyRequests),
  });
