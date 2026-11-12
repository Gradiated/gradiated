import { APIError } from "better-auth/api";
import { oauthProviderAuthServerMetadata } from "@better-auth/oauth-provider";
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
  mcpOAuthProvider,
  nativeLoopbackRegistration,
  type OAuthConfiguration,
  type OAuthServerApi,
} from "./oauth.js";
import {
  STAFF_SESSION_RECOVERY_CODE,
  StaffSessionRecoveryRequired,
} from "./errors.js";

import type { MagicLinkSender, OtpCodeSender } from "../email/auth-messages.js";
import { ApiProblem, problems } from "../http/problems.js";
import type { AuthService } from "../types.js";

export interface AuthConfiguration {
  baseUrl: string;
  oauth: OAuthConfiguration;
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

type GithubAccountApi = {
  listUserAccounts(input: {
    headers: Headers;
  }): Promise<{ id: string; providerId: string }[]>;
  getAccessToken(input: {
    headers: Headers;
    body: { accountId: string };
  }): Promise<{ accessToken?: string | undefined }>;
};

export const readGithubAccessToken = async (
  api: GithubAccountApi,
  headers: Headers,
) => {
  const accounts = await api.listUserAccounts({ headers });
  const github = accounts.filter((account) => account.providerId === "github");
  if (!github[0]) return null;

  if (github.length > 1)
    throw new ApiProblem(
      problems.conflict(
        "More than one GitHub account is linked to this user. Contact Gradiated to unlink one.",
      ),
    );

  const result = await api.getAccessToken({
    headers,
    body: { accountId: github[0].id },
  });

  return result.accessToken ?? null;
};

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
    session: {
      additionalFields: {
        oauthWorkspaceId: { type: "string", required: false, input: false },
      },
    },
    account: {
      accountLinking: {
        enabled: true,
        /* Only linking the signed-in user starts (linkSocial), bound to their
           session by the OAuth state. Customers connect GitHub to verify app
           installations, and their GitHub email often differs from their work
           email. Sign-in still links implicitly only on a verified match. */
        allowDifferentEmails: true,
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
      nativeLoopbackRegistration,
      mcpOAuthProvider(configuration.oauth),
    ],
  });
  const authorizationServerMetadata = oauthProviderAuthServerMetadata(
    auth as unknown as OAuthServerApi,
    {
      headers: { "Access-Control-Allow-Origin": "*" },
    },
  );

  return {
    githubAccessToken: async (headers) =>
      configuration.github ? readGithubAccessToken(auth.api, headers) : null,
    handler: (request) => auth.handler(request),
    authorizationServerMetadata,
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
        sessionId: result.session.id,
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
