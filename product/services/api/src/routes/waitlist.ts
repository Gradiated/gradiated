import { problemContent } from "@gradiated/contracts";
import { waitlistSignupSchema, type WaitlistService } from "@gradiated/control";
import { createRoute, type OpenAPIHono, z } from "@hono/zod-openapi";

import { serviceLog } from "../logging.js";
import type { ApiEnvironment } from "../types.js";
import type { WaitlistWelcomeSender } from "../email/waitlist-welcome.js";

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
      content: { "application/json": { schema: waitlistSignupSchema } },
    },
  },
  responses: {
    200: {
      description:
        "The signup is recorded. Returned for repeat emails too, so the endpoint does not reveal who is already on the list.",
      content: { "application/json": { schema: WaitlistResponseSchema } },
    },
    422: {
      description: "The request body is invalid.",
      content: problemContent,
    },
  },
});

export const registerWaitlistRoutes = (
  app: OpenAPIHono<ApiEnvironment>,
  {
    waitlist,
    sendWelcome,
  }: {
    waitlist: Pick<WaitlistService, "join">;
    sendWelcome: WaitlistWelcomeSender;
  },
): void => {
  app.openapi(joinWaitlistRoute, async (context) => {
    const outcome = await waitlist.join(context.req.valid("json"));

    if (outcome.created) {
      void sendWelcome({ email: outcome.email }).catch((error) => {
        serviceLog("error", "welcome_email_failed", { error });
      });
    }

    return context.json({ status: "ok" as const }, 200);
  });
};
