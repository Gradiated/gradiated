import type { Hono } from "hono";

import type { ApiEnvironment } from "../types.js";

export interface AuthTestMailbox {
  takeMagicLink(email: string): string | null;
  takeOtp(email: string): string | null;
}

const takeRoutes = [
  {
    path: "/api/auth/test/magic-link",
    field: "url",
    missing: "Link not found.",
    take: "takeMagicLink",
  },
  {
    path: "/api/auth/test/otp",
    field: "code",
    missing: "Code not found.",
    take: "takeOtp",
  },
] as const satisfies readonly {
  path: string;
  field: string;
  missing: string;
  take: keyof AuthTestMailbox;
}[];

export const registerAuthTestRoutes = (
  app: Hono<ApiEnvironment>,
  mailbox: AuthTestMailbox,
): void => {
  for (const { path, field, missing, take } of takeRoutes) {
    app.get(path, (context) => {
      const email = context.req.query("email");
      if (!email) return context.json({ error: "Email is required." }, 400);

      const value = mailbox[take](email);
      if (!value) return context.json({ error: missing }, 404);

      return context.json({ [field]: value });
    });
  }
};
