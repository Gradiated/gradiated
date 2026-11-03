import {
  ImpersonationInputSchema,
  ImpersonationResultSchema,
  problemContent,
} from "@gradiated/contracts";
import { createRoute, type OpenAPIHono } from "@hono/zod-openapi";

import { ApiProblem, problems, requireUser } from "../http/problems.js";
import { consoleOnly } from "../http/audience.js";
import type { ApiEnvironment, AuthService } from "../types.js";

export const registerImpersonationRoutes = (
  app: OpenAPIHono<ApiEnvironment>,
  auth: AuthService,
) => {
  for (const operation of [
    {
      path: "/api/v1/admin/impersonations",
      authPath: "/staff/impersonate-user",
      operationId: "startImpersonation",
      summary: "View the console as a customer user",
      start: true,
    },
    {
      path: "/api/v1/admin/impersonations/stop",
      authPath: "/staff/stop-impersonating",
      operationId: "stopImpersonation",
      summary: "Return to the original staff session",
      start: false,
    },
  ] as const) {
    app.openapi(
      createRoute({
        ...consoleOnly,
        method: "post",
        path: operation.path,
        operationId: operation.operationId,
        summary: operation.summary,
        description: operation.start
          ? "Verified staff may create a short-lived customer session. The original staff session is retained for returning."
          : "Deletes the impersonation session and restores the original staff session.",
        tags: ["Session"],
        request: operation.start
          ? {
              body: {
                required: true,
                content: {
                  "application/json": { schema: ImpersonationInputSchema },
                },
              },
            }
          : {},
        responses: {
          200: {
            description: "Session switched.",
            content: {
              "application/json": { schema: ImpersonationResultSchema },
            },
          },
          401: {
            description: "Authentication required.",
            content: problemContent,
          },
          403: {
            description: "Staff access or target denied.",
            content: problemContent,
          },
          404: { description: "User not found.", content: problemContent },
          422: { description: "Invalid target.", content: problemContent },
        },
      }),
      async (context) => {
        context.header("Cache-Control", "no-store");

        if (operation.start) {
          const user = await requireUser(context);
          if (!user.isStaff || !user.emailVerified || user.impersonatedBy)
            throw new ApiProblem(
              problems.forbidden("Verified staff access is required."),
            );
        } else if (!context.req.header("Cookie")) {
          throw new ApiProblem(problems.unauthenticated);
        }

        const url = new URL(context.req.url);
        url.pathname = `/api/auth${operation.authPath}`;

        const response = await auth.handler(
          new Request(url, {
            method: "POST",
            headers: context.req.raw.headers,
            body: operation.start ? await context.req.text() : null,
          }),
        );
        if (response.status === 401)
          throw new ApiProblem(problems.unauthenticated);
        if (response.status === 403)
          throw new ApiProblem(
            problems.forbidden(
              "Staff access is required and the target must be a verified customer user.",
            ),
          );
        if (response.status === 404)
          throw new ApiProblem(problems.notFound("User not found."));
        if (response.status === 400 || response.status === 422)
          throw new ApiProblem(
            problems.validation([
              { path: "user_id", message: "Invalid impersonation request." },
            ]),
          );
        if (!response.ok)
          throw new ApiProblem(
            problems.unavailable("The session could not be switched."),
          );

        for (const cookie of response.headers.getSetCookie())
          context.header("Set-Cookie", cookie, { append: true });

        return context.json(
          ImpersonationResultSchema.parse(await response.json()),
          200,
        );
      },
    );
  }
};
