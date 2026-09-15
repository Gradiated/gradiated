import { COMPANY_SIZES } from "@gradiated/control";
import { createRoute, type OpenAPIHono, z } from "@hono/zod-openapi";

import type { ApiEnvironment, ApiServices } from "../types.js";
import type { WaitlistWelcomeSender } from "../waitlist-email.js";

const WaitlistRequestSchema = z
  .object({
    email: z.string().trim().toLowerCase().email().max(320).openapi({
      example: "name@example.com",
    }),
    companySize: z.enum(COMPANY_SIZES),
    monthlyTokenSpendUsd: z.string().trim().min(1).max(100),
    motivation: z.string().trim().min(1).max(4000),
  })
  .openapi("WaitlistRequest");

const WaitlistResponseSchema = z
  .object({ status: z.literal("ok") })
  .openapi("WaitlistResponse");

const joinWaitlistRoute = createRoute({
  hide: true,
  method: "post",
  path: "/api/v1/waitlist",
  operationId: "joinWaitlist",
  tags: ["Waitlist"],
  request: {
    body: {
      required: true,
      content: { "application/json": { schema: WaitlistRequestSchema } },
    },
  },
  responses: {
    200: {
      description:
        "The signup is recorded. Returned for repeat emails too, so the endpoint does not reveal who is already on the list.",
      content: { "application/json": { schema: WaitlistResponseSchema } },
    },
    422: {
      description:
        "Validation problem, via the app-wide defaultHook — the framework validates the body before the handler runs.",
      content: undefined as never,
    },
  },
});

/**
 * Public — the one unauthenticated write in the API, which shapes it:
 * validation is strict, the response says nothing about existing rows, and
 * the welcome email is sent AFTER the response and only for a first signup.
 * A slow or failing email provider must never make the form look broken,
 * and a resubmitted email must never trigger a second welcome.
 */
export function registerWaitlistRoutes(
  app: OpenAPIHono<ApiEnvironment>,
  services: ApiServices,
  sendWelcome: WaitlistWelcomeSender,
) {
  app.openapi(joinWaitlistRoute, async (context) => {
    /* The route schema has already validated the body — the app's defaultHook
       turns a mismatch into the 422 problem before this runs. The service
       re-parses, but on data that has already passed the same shape. */
    const outcome = await services.waitlist.join(context.req.valid("json"));

    if (outcome.created) {
      void sendWelcome({ email: outcome.email }).catch((error) => {
        console.error(
          `[waitlist] welcome email failed for a new signup: ${String(error)}`,
        );
      });
    }
    return context.json({ status: "ok" as const }, 200);
  });
}
