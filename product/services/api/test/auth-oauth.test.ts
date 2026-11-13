import { createHash, randomBytes } from "node:crypto";

import type { ControlDatabase } from "@gradiated/control";
import { beforeEach, expect, it, vi } from "vitest";

import { createAuthService } from "../src/auth/service.js";

const records = vi.hoisted(() => ({
  user: [] as Record<string, unknown>[],
  session: [] as Record<string, unknown>[],
  account: [] as Record<string, unknown>[],
  verification: [] as Record<string, unknown>[],
  oauthClient: [] as Record<string, unknown>[],
  oauthResource: [] as Record<string, unknown>[],
  oauthClientResource: [] as Record<string, unknown>[],
  oauthRefreshToken: [] as Record<string, unknown>[],
  oauthAccessToken: [] as Record<string, unknown>[],
  oauthConsent: [] as Record<string, unknown>[],
  oauthClientAssertion: [] as Record<string, unknown>[],
}));

vi.mock("better-auth/adapters/drizzle", async () => {
  const { memoryAdapter } = await import("better-auth/adapters/memory");

  return { drizzleAdapter: () => memoryAdapter(records) };
});

beforeEach(() => {
  for (const rows of Object.values(records)) rows.length = 0;
});

const baseUrl = "http://localhost:3000";
const consoleUrl = "http://localhost:5173";
const mcpResource = "http://localhost:3007/mcp";
const redirectUri = "http://127.0.0.1:33418/callback";
const workspaceId = "0198ae5a-2529-7c1a-801b-dc9d5f876a94";

const createHarness = () => {
  let code = "";
  const auth = createAuthService({} as ControlDatabase, {
    baseUrl,
    oauth: { consoleUrl, mcpResource },
    secret: "local-only-not-secret-change-in-production-0001",
    trustedOrigins: [baseUrl, consoleUrl],
    onUserCreated: async () => undefined,
    sendMagicLink: async () => undefined,
    sendOtp: async (message) => {
      code = message.code;
    },
  });
  const request = (
    path: string,
    init: {
      method?: string;
      body?: unknown;
      cookie?: string;
      form?: boolean;
    } = {},
  ) =>
    auth.handler(
      new Request(`${baseUrl}/api/auth${path}`, {
        method: init.method ?? (init.body === undefined ? "GET" : "POST"),
        redirect: "manual",
        headers: {
          Origin: consoleUrl,
          Cookie: init.cookie ?? "",
          Accept: "application/json",
          ...(init.body === undefined
            ? {}
            : {
                "Content-Type": init.form
                  ? "application/x-www-form-urlencoded"
                  : "application/json",
              }),
        },
        ...(init.body === undefined
          ? {}
          : {
              body: init.form
                ? new URLSearchParams(init.body as Record<string, string>)
                : JSON.stringify(init.body),
            }),
      }),
    );
  const signIn = async () => {
    const email = "member@example.com";
    await request("/email-otp/send-verification-otp", {
      body: { email, type: "sign-in" },
    });
    const response = await request("/sign-in/email-otp", {
      body: { email, otp: code, name: "Member" },
    });

    return response.headers
      .getSetCookie()
      .map((cookie) => cookie.split(";")[0])
      .join("; ");
  };

  return { auth, request, signIn };
};

const redirectLocation = async (response: Response) => {
  const location =
    response.headers.get("location") ??
    ((await response.json()) as { url?: string; redirect_uri?: string }).url ??
    "";

  return new URL(location);
};

it("issues a workspace-bound opaque token to a dynamically registered MCP client", async () => {
  const { auth, request, signIn } = createHarness();

  const registered = await request("/oauth2/register", {
    body: {
      client_name: "Claude",
      redirect_uris: [redirectUri],
      token_endpoint_auth_method: "none",
      grant_types: ["authorization_code", "refresh_token"],
    },
  });
  expect(registered.status).toBe(201);
  const { client_id: clientId } = (await registered.json()) as {
    client_id: string;
  };

  const cookie = await signIn();
  const verifier = randomBytes(32).toString("base64url");
  const authorize = new URLSearchParams({
    response_type: "code",
    client_id: clientId,
    redirect_uri: redirectUri,
    scope: "mcp offline_access",
    state: "state-1",
    code_challenge: createHash("sha256").update(verifier).digest("base64url"),
    code_challenge_method: "S256",
    resource: mcpResource,
  });

  const consentPage = await redirectLocation(
    await request(`/oauth2/authorize?${authorize}`, { cookie }),
  );
  expect(`${consentPage.origin}${consentPage.pathname}`).toBe(
    `${consoleUrl}/oauth/consent`,
  );

  // The console's workspace selection, which the API route performs through the control service.
  records.session[0]!.oauthWorkspaceId = workspaceId;
  const callback = await redirectLocation(
    await request("/oauth2/consent", {
      cookie,
      body: { accept: true, oauth_query: consentPage.search.slice(1) },
    }),
  );
  expect(`${callback.origin}${callback.pathname}`).toBe(redirectUri);
  expect(callback.searchParams.get("state")).toBe("state-1");

  const token = await request("/oauth2/token", {
    form: true,
    body: {
      grant_type: "authorization_code",
      code: callback.searchParams.get("code")!,
      redirect_uri: redirectUri,
      client_id: clientId,
      code_verifier: verifier,
      resource: mcpResource,
    },
  });
  expect(token.status).toBe(200);
  const { access_token: accessToken } = (await token.json()) as {
    access_token: string;
  };

  expect(accessToken).toMatch(/^grado_[A-Za-z]{32}$/);
  expect(records.oauthAccessToken).toEqual([
    expect.objectContaining({
      token: createHash("sha256")
        .update(accessToken.slice("grado_".length))
        .digest("base64url"),
      referenceId: workspaceId,
      scopes: ["mcp", "offline_access"],
    }),
  ]);

  const metadata = await auth.authorizationServerMetadata(
    new Request(`${baseUrl}/.well-known/oauth-authorization-server/api/auth`),
  );
  expect(await metadata.json()).toMatchObject({
    issuer: `${baseUrl}/api/auth`,
    registration_endpoint: `${baseUrl}/api/auth/oauth2/register`,
    code_challenge_methods_supported: ["S256"],
  });
});

it("sends a session without a chosen workspace to the consent page", async () => {
  const { request, signIn } = createHarness();
  const registered = await request("/oauth2/register", {
    body: {
      redirect_uris: [redirectUri],
      token_endpoint_auth_method: "none",
    },
  });
  const { client_id: clientId } = (await registered.json()) as {
    client_id: string;
  };
  const cookie = await signIn();
  records.oauthConsent.push({
    id: "0198ae5a-2529-7c1a-801b-dc9d5f876a99",
    clientId,
    userId: records.user[0]!.id,
    scopes: ["mcp", "offline_access"],
    createdAt: new Date(),
    updatedAt: new Date(),
  });

  const page = await redirectLocation(
    await request(
      `/oauth2/authorize?${new URLSearchParams({
        response_type: "code",
        client_id: clientId,
        redirect_uri: redirectUri,
        scope: "mcp offline_access",
        code_challenge: "a".repeat(43),
        code_challenge_method: "S256",
      })}`,
      { cookie },
    ),
  );

  expect(page.pathname).toBe("/oauth/consent");
});
