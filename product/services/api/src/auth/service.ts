import { betterAuth } from "better-auth";
import { drizzleAdapter } from "better-auth/adapters/drizzle";
import { emailOTP, magicLink, openAPI } from "better-auth/plugins";
import { v7 as uuidv7 } from "uuid";

import { betterAuthSchema, type ControlDatabase } from "@gradiated/control";

import type { MagicLinkSender, OtpCodeSender } from "../email/auth-messages.js";
import type { AuthService } from "../types.js";

export interface AuthConfiguration {
  baseUrl: string;
  github?: { clientId: string; clientSecret: string } | undefined;
  google?: { clientId: string; clientSecret: string } | undefined;
  onUserCreated: (user: { id: string; name: string }) => Promise<void>;
  secret: string;
  sendMagicLink: MagicLinkSender;
  sendOtp: OtpCodeSender;
  trustedOrigins: string[];
}

const DEVELOPMENT_TRUSTED_ORIGINS = [
  "http://localhost:5173",
  "http://127.0.0.1:5173",
] as const;

export const resolveAuthTrustedOrigins = (
  configuredOrigins: readonly string[],
  nodeEnvironment: string | undefined,
): string[] => [
  ...new Set([
    ...configuredOrigins,
    ...(nodeEnvironment === "production" ? [] : DEVELOPMENT_TRUSTED_ORIGINS),
  ]),
];

export const createAuthService = (
  database: ControlDatabase,
  configuration: AuthConfiguration,
): AuthService => {
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
      ...(configuration.github ? { github: configuration.github } : {}),
      ...(configuration.google ? { google: configuration.google } : {}),
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
      emailOTP({
        expiresIn: 600,
        otpLength: 6,
        sendVerificationOTP: ({ email, otp }) =>
          configuration.sendOtp({ code: otp, email }),
        storeOTP: "hashed",
      }),
      openAPI({ disableDefaultReference: true }),
    ],
  });

  return {
    handler: (request) => auth.handler(request),
    resolveSession: async (headers) => {
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
};
