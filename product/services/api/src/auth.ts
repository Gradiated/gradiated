import { betterAuth } from "better-auth";
import { drizzleAdapter } from "better-auth/adapters/drizzle";
import { magicLink, openAPI } from "better-auth/plugins";
import { v7 as uuidv7 } from "uuid";

import { betterAuthSchema, type ControlDatabase } from "@gradiated/control";

import type { AuthService } from "./types.js";
import type { MagicLinkSender } from "./auth-email.js";

export interface AuthConfiguration {
  baseUrl: string;
  github?: { clientId: string; clientSecret: string } | undefined;
  google?: { clientId: string; clientSecret: string } | undefined;
  onUserCreated: (user: { id: string; name: string }) => Promise<void>;
  secret: string;
  sendMagicLink: MagicLinkSender;
  takeTestMagicLink?: ((email: string) => string | null) | undefined;
  trustedOrigins: string[];
}

export function createAuthService(
  database: ControlDatabase,
  configuration: AuthConfiguration,
): AuthService {
  const auth = betterAuth({
    appName: "Gradiated",
    basePath: "/api/auth",
    baseURL: configuration.baseUrl,
    secret: configuration.secret,
    trustedOrigins: configuration.trustedOrigins,
    database: drizzleAdapter(database, {
      provider: "pg",
      schema: betterAuthSchema,
    }),
    account: {
      accountLinking: {
        enabled: true,
        allowDifferentEmails: false,
      },
    },
    socialProviders: {
      ...(configuration.github
        ? {
            github: {
              clientId: configuration.github.clientId,
              clientSecret: configuration.github.clientSecret,
            },
          }
        : {}),
      ...(configuration.google
        ? {
            google: {
              clientId: configuration.google.clientId,
              clientSecret: configuration.google.clientSecret,
            },
          }
        : {}),
    },
    databaseHooks: {
      user: {
        create: {
          after: configuration.onUserCreated,
        },
      },
    },
    advanced: {
      database: {
        generateId: () => uuidv7(),
      },
    },
    plugins: [
      magicLink({
        expiresIn: 600,
        sendMagicLink: configuration.sendMagicLink,
        storeToken: "hashed",
      }),
      openAPI({ disableDefaultReference: true }),
    ],
  });

  return {
    handler: (request) => auth.handler(request),
    ...(configuration.takeTestMagicLink
      ? { takeTestMagicLink: configuration.takeTestMagicLink }
      : {}),
    async resolveSession(headers) {
      const result = await auth.api.getSession({ headers });
      if (!result) return null;

      return {
        id: result.user.id,
        name: result.user.name,
        email: result.user.email,
        emailVerified: result.user.emailVerified,
        image: result.user.image ?? null,
        createdAt: result.user.createdAt,
      };
    },
  };
}
