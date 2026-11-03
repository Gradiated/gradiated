import type { AuthContext, BetterAuthPlugin } from "better-auth";
import {
  APIError,
  createAuthEndpoint,
  createAuthMiddleware,
  getSessionFromCtx,
  sessionMiddleware,
  originCheckMiddleware,
} from "better-auth/api";
import {
  deleteSessionCookie,
  expireCookie,
  setSessionCookie,
} from "better-auth/cookies";
import { z } from "@hono/zod-openapi";

import { STAFF_SESSION_RECOVERY_CODE } from "./errors.js";

import { serviceLog } from "../logging.js";

export const IMPERSONATION_DURATION_MS = 15 * 60 * 1000;

const staffIdentity = z.object({
  isStaff: z.literal(true),
  emailVerified: z.literal(true),
});
const impersonationFields = z.object({
  impersonatedBy: z.string().nullish(),
  impersonatorSessionId: z.string().nullish(),
  createdAt: z.coerce.date(),
  expiresAt: z.coerce.date(),
});

export const impersonationIsActive = async (
  context: {
    adapter: Pick<AuthContext["adapter"], "findOne">;
    internalAdapter: Pick<AuthContext["internalAdapter"], "findUserById">;
  },
  session: { session: unknown; user: { id: string } },
): Promise<boolean> => {
  const metadata = impersonationFields.parse(session.session);
  if (!metadata.impersonatedBy) return true;
  if (
    !metadata.impersonatorSessionId ||
    metadata.expiresAt.getTime() <= Date.now() ||
    metadata.createdAt.getTime() + IMPERSONATION_DURATION_MS <= Date.now()
  )
    return false;

  const actor = await context.internalAdapter.findUserById(
    metadata.impersonatedBy,
  );
  const original = await context.adapter.findOne<{
    userId: string;
    expiresAt: Date;
    impersonatedBy?: string | null;
  }>({
    model: "session",
    where: [{ field: "id", value: metadata.impersonatorSessionId }],
  });
  const target = await context.internalAdapter.findUserById(session.user.id);

  return (
    staffIdentity.safeParse(actor).success &&
    !!original &&
    original.userId === metadata.impersonatedBy &&
    !original.impersonatedBy &&
    original.expiresAt > new Date() &&
    !!target &&
    target.emailVerified &&
    !staffIdentity.safeParse(target).success
  );
};

export const staffImpersonation = () =>
  ({
    id: "staff-impersonation",
    schema: {
      session: {
        fields: {
          impersonatedBy: { type: "string", required: false, input: false },
          impersonatorSessionId: {
            type: "string",
            required: false,
            input: false,
          },
        },
      },
    },
    hooks: {
      before: [
        {
          matcher: (context) => context.path !== "/staff/stop-impersonating",
          handler: createAuthMiddleware(async (context) => {
            if (context.path === "/sign-out") {
              if (context.request)
                await originCheckMiddleware({
                  ...context,
                  request: context.request,
                  headers: context.request.headers,
                });

              const retainedCookie =
                context.context.createAuthCookie("staff_session");
              const retained = await context.getSignedCookie(
                retainedCookie.name,
                context.context.secret,
              );
              if (retained) {
                const [token] = retained.split(":");
                const original = token
                  ? await context.context.internalAdapter.findSession(token)
                  : null;
                const activeToken = await context.getSignedCookie(
                  context.context.authCookies.sessionToken.name,
                  context.context.secret,
                );
                if (token)
                  await context.context.internalAdapter.deleteSession(token);
                if (activeToken)
                  await context.context.internalAdapter.deleteSession(
                    activeToken,
                  );
                expireCookie(context, retainedCookie);
                serviceLog("info", "staff_impersonation_signed_out", {
                  actor_user_id: original?.user.id,
                });
              }

              return;
            }

            const session = await getSessionFromCtx(context);
            const metadata = session
              ? impersonationFields.parse(session.session)
              : null;
            const expired =
              !session ||
              (metadata?.impersonatedBy &&
                (metadata.expiresAt.getTime() <= Date.now() ||
                  metadata.createdAt.getTime() + IMPERSONATION_DURATION_MS <=
                    Date.now()));
            if (context.path === "/get-session" && expired) {
              const retainedCookie =
                context.context.createAuthCookie("staff_session");
              const retained = await context.getSignedCookie(
                retainedCookie.name,
                context.context.secret,
              );
              const token = retained ? retained.split(":")[0] : undefined;
              const original = token
                ? await context.context.internalAdapter.findSession(token)
                : null;
              if (
                original &&
                staffIdentity.safeParse(original.user).success &&
                original.session.expiresAt > new Date() &&
                !impersonationFields.parse(original.session).impersonatedBy
              )
                throw new APIError("UNAUTHORIZED", {
                  code: STAFF_SESSION_RECOVERY_CODE,
                  message:
                    "Restore the retained staff session before continuing.",
                });
            }
            if (
              session &&
              !(await impersonationIsActive(context.context, session))
            )
              throw new APIError("UNAUTHORIZED", {
                message: "The impersonation session is no longer authorized.",
              });
            if (session && context.method === "POST") {
              const metadata = impersonationFields.parse(session.session);
              if (metadata.impersonatedBy)
                serviceLog("info", "staff_impersonation_auth_request", {
                  actor_user_id: metadata.impersonatedBy,
                  user_id: session.user.id,
                  route: context.path,
                  method: context.method,
                });
            }
          }),
        },
      ],
    },
    endpoints: {
      impersonateUser: createAuthEndpoint(
        "/staff/impersonate-user",
        {
          method: "POST",
          body: z.strictObject({ user_id: z.uuid() }),
          use: [originCheckMiddleware, sessionMiddleware],
        },
        async (context) => {
          const current = context.context.session;
          if (
            !staffIdentity.safeParse(current.user).success ||
            impersonationFields.parse(current.session).impersonatedBy
          )
            throw new APIError("FORBIDDEN", {
              message: "Verified staff access is required.",
            });

          const target = await context.context.internalAdapter.findUserById(
            context.body.user_id,
          );
          if (!target)
            throw new APIError("NOT_FOUND", { message: "User not found." });
          if (
            target.id === current.user.id ||
            staffIdentity.safeParse(target).success ||
            !target.emailVerified
          )
            throw new APIError("FORBIDDEN", {
              message: "Choose a verified customer user.",
            });

          const session = await context.context.internalAdapter.createSession(
            target.id,
            true,
            {
              impersonatedBy: current.user.id,
              impersonatorSessionId: current.session.id,
              expiresAt: new Date(Date.now() + IMPERSONATION_DURATION_MS),
            },
            true,
          );
          if (!session)
            throw new APIError("INTERNAL_SERVER_ERROR", {
              message: "Could not start impersonation.",
            });

          const originalCookie =
            context.context.createAuthCookie("staff_session");
          const dontRemember = await context.getSignedCookie(
            context.context.authCookies.dontRememberToken.name,
            context.context.secret,
          );
          deleteSessionCookie(context);
          await context.setSignedCookie(
            originalCookie.name,
            `${current.session.token}:${dontRemember || ""}`,
            context.context.secret,
            originalCookie.attributes,
          );
          await setSessionCookie(context, { session, user: target }, true);
          serviceLog("info", "staff_impersonation_started", {
            actor_user_id: current.user.id,
            user_id: target.id,
          });

          return context.json({ user_id: target.id });
        },
      ),
      stopImpersonating: createAuthEndpoint(
        "/staff/stop-impersonating",
        {
          method: "POST",
          requireHeaders: true,
          use: [originCheckMiddleware],
        },
        async (context) => {
          const originalCookie =
            context.context.createAuthCookie("staff_session");
          const originalValue = await context.getSignedCookie(
            originalCookie.name,
            context.context.secret,
          );
          if (!originalValue)
            throw new APIError("UNAUTHORIZED", {
              message: "Staff session not found.",
            });

          const [token, dontRemember] = originalValue.split(":");
          const original = token
            ? await context.context.internalAdapter.findSession(token)
            : null;
          if (
            !original ||
            original.session.expiresAt <= new Date() ||
            impersonationFields.parse(original.session).impersonatedBy
          )
            throw new APIError("UNAUTHORIZED", {
              message: "Sign in to your staff account again.",
            });

          const current = await getSessionFromCtx(context);
          if (
            current &&
            impersonationFields.parse(current.session).impersonatedBy ===
              original.user.id
          )
            await context.context.internalAdapter.deleteSession(
              current.session.token,
            );

          await setSessionCookie(context, original, !!dontRemember);
          expireCookie(context, originalCookie);
          serviceLog("info", "staff_impersonation_stopped", {
            actor_user_id: original.user.id,
            user_id: current?.user.id,
          });

          return context.json({ user_id: original.user.id });
        },
      ),
    },
  }) satisfies BetterAuthPlugin;
