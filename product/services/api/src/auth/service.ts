import { APIError } from "better-auth/api";
import { betterAuth } from "better-auth";
import { drizzleAdapter } from "better-auth/adapters/drizzle";
import { emailOTP, magicLink, openAPI } from "better-auth/plugins";
import { v7 as uuidv7 } from "uuid";

import { betterAuthSchema, type ControlDatabase } from "@gradiated/control";

import {
  staffImpersonation,
  IMPERSONATION_DURATION_MS,
} from "./impersonation.js";

import {
  STAFF_SESSION_RECOVERY_CODE,
  StaffSessionRecoveryRequired,
} from "./errors.js";

import type { MagicLinkSender, OtpCodeSender } from "../email/auth-messages.js";
import type { AuthService } from "../types.js";

export interface AuthConfiguration {
  baseUrl: string;
  github?: { clientId: string; clientSecret: string } | undefined;
  google?: { clientId: string; clientSecret: string } | undefined;
  onUserCreated: (user: {
    id: string;
    name: string;
    email: string;
    emailVerified: boolean;
  }) => Promise<void>;
  onSessionCreated?: (session: { id: string; userId: string }) => Promise<void>;
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
    user: {
      additionalFields: {
        isStaff: { type: "boolean", defaultValue: false, input: false },
      },
    },
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
      ...(configuration.onSessionCreated
        ? {
            session: {
              create: {
                after: async (session) => {
                  if (!Reflect.get(session, "impersonatedBy"))
                    await configuration.onSessionCreated?.(session);
                },
              },
            },
          }
        : {}),
      user: {
        create: {
          after: configuration.onUserCreated,
        },
      },
    },
    advanced: {
      disableOriginCheck: false,
      disableCSRFCheck: false,
      database: {
        generateId: () => uuidv7(),
      },
    },
    plugins: [
      staffImpersonation(),
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
      const result = await auth.api
        .getSession({ headers })
        .catch((error: unknown) => {
          if (error instanceof APIError && error.status === "UNAUTHORIZED") {
            if (error.body?.code === STAFF_SESSION_RECOVERY_CODE)
              throw new StaffSessionRecoveryRequired();

            return null;
          }

          throw error;
        });
      if (!result) return null;

      return {
        id: result.user.id,
        name: result.user.name,
        email: result.user.email,
        emailVerified: result.user.emailVerified,
        isStaff: result.user.isStaff,
        impersonatedBy: result.session.impersonatedBy ?? null,
        impersonationExpiresAt: result.session.impersonatedBy
          ? new Date(
              Math.min(
                result.session.expiresAt.getTime(),
                result.session.createdAt.getTime() + IMPERSONATION_DURATION_MS,
              ),
            )
          : null,
        image: result.user.image ?? null,
        createdAt: result.user.createdAt,
      };
    },
  };
};
