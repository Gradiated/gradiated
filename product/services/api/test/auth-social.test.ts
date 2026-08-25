import { describe, expect, it } from "vitest";

import type { ControlDatabase } from "@gradiated/control";

import { createAuthService } from "../src/auth.js";

const createSocialAuth = () =>
  createAuthService(
    {
      insert: () => ({
        values: (values: Record<string, unknown>) => ({
          returning: async () => [values],
        }),
      }),
    } as unknown as ControlDatabase,
    {
      baseUrl: "http://localhost:3000",
      github: {
        clientId: "github-client-id",
        clientSecret: "github-client-secret",
      },
      google: {
        clientId: "google-client-id",
        clientSecret: "google-client-secret",
      },
      onUserCreated: async () => undefined,
      secret: "local-only-not-secret-change-in-production-0001",
      sendMagicLink: async () => undefined,
      trustedOrigins: ["http://localhost:3000"],
    },
  );

describe("social authentication providers", () => {
  it.each([
    {
      provider: "github" as const,
      clientId: "github-client-id",
      authorizationHost: "github.com",
    },
    {
      provider: "google" as const,
      clientId: "google-client-id",
      authorizationHost: "accounts.google.com",
    },
  ])(
    "creates the $provider authorization URL",
    async ({ provider, clientId, authorizationHost }) => {
      const auth = createSocialAuth();
      const response = await auth.handler(
        new Request("http://localhost:3000/api/auth/sign-in/social", {
          method: "POST",
          headers: {
            "content-type": "application/json",
            origin: "http://localhost:3000",
          },
          body: JSON.stringify({
            provider,
            callbackURL: "http://localhost:3000/api-keys",
            errorCallbackURL: "http://localhost:3000/login",
            newUserCallbackURL: "http://localhost:3000/api-keys",
            disableRedirect: true,
          }),
        }),
      );

      expect(response.status).toBe(200);
      const body = (await response.json()) as {
        url: string;
        redirect: boolean;
      };
      const authorizationURL = new URL(body.url);

      expect(body.redirect).toBe(false);
      expect(authorizationURL.hostname).toBe(authorizationHost);
      expect(authorizationURL.searchParams.get("client_id")).toBe(clientId);
      expect(authorizationURL.searchParams.get("redirect_uri")).toBe(
        "http://localhost:3000/api/auth/callback/" + provider,
      );
    },
  );
});
