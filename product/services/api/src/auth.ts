import { betterAuth } from "better-auth";
import { drizzleAdapter } from "better-auth/adapters/drizzle";
import { openAPI } from "better-auth/plugins";
import { v7 as uuidv7 } from "uuid";

import { betterAuthSchema, type ControlDatabase } from "@gradiated/control";

import type { AuthService } from "./types.js";

export interface AuthConfiguration {
  baseUrl: string;
  minPasswordLength: number;
  secret: string;
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
    emailAndPassword: {
      enabled: true,
      minPasswordLength: configuration.minPasswordLength,
    },
    advanced: {
      database: {
        generateId: () => uuidv7(),
      },
    },
    plugins: [openAPI({ disableDefaultReference: true })],
  });

  return {
    handler: (request) => auth.handler(request),
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
