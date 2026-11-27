import { createPublicKey, verify, type JsonWebKey } from "node:crypto";

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
  jwks: [] as Record<string, unknown>[],
}));

vi.mock("better-auth/adapters/drizzle", async () => {
  const { memoryAdapter } = await import("better-auth/adapters/memory");

  return { drizzleAdapter: () => memoryAdapter(records) };
});

beforeEach(() => {
  for (const rows of Object.values(records)) rows.length = 0;
});

const baseUrl = "https://api.gradiated.test";
const subject = {
  userId: "0198ae50-94d8-7d4d-a8be-9f9b44b8c774",
  organizationId: "0198ae5a-1c62-7b2b-9df2-29d8a5d7d3a4",
  workspaceId: "0198ae5a-2529-7c1a-801b-dc9d5f876a94",
  role: "admin" as const,
};

const createAuth = () =>
  createAuthService({} as ControlDatabase, {
    baseUrl,
    oauth: {
      consoleUrl: "https://console.gradiated.test",
      mcpResource: "https://mcp.gradiated.test/mcp",
    },
    secret: "local-only-not-secret-change-in-production-0001",
    trustedOrigins: [baseUrl],
    onUserCreated: async () => undefined,
    sendMagicLink: async () => undefined,
    sendOtp: async () => undefined,
  });

const decode = (part: string) =>
  JSON.parse(Buffer.from(part, "base64url").toString("utf8")) as Record<
    string,
    unknown
  >;

const jwks = async (auth: ReturnType<typeof createAuth>) => {
  const response = await auth.handler(new Request(`${baseUrl}/api/auth/jwks`));
  expect(response.status).toBe(200);

  return ((await response.json()) as { keys: (JsonWebKey & { kid: string })[] })
    .keys;
};

it("signs an ES256 training token that the published keys verify", async () => {
  const auth = createAuth();

  const { token, expiresAt } = await auth.signTrainingToken(subject);

  const [header = "", payload = "", signature = ""] = token.split(".");
  const claims = decode(payload);
  const keys = await jwks(auth);
  const key = keys.find((candidate) => candidate.kid === decode(header).kid);

  expect(decode(header)).toMatchObject({ alg: "ES256" });
  expect(key).toMatchObject({ kty: "EC", crv: "P-256", alg: "ES256" });
  expect(key).not.toHaveProperty("d");
  expect(
    verify(
      "sha256",
      Buffer.from(`${header}.${payload}`),
      {
        key: createPublicKey({ key: key!, format: "jwk" }),
        dsaEncoding: "ieee-p1363",
      },
      Buffer.from(signature, "base64url"),
    ),
  ).toBe(true);
  expect(claims).toEqual({
    iss: baseUrl,
    aud: "training",
    sub: `user:${subject.userId}`,
    org: subject.organizationId,
    ws: subject.workspaceId,
    role: "admin",
    jti: expect.any(String),
    iat: expect.any(Number),
    exp: (claims.iat as number) + 600,
  });
  expect(expiresAt.getTime()).toBe((claims.exp as number) * 1000);
});

it("signs every token with one key until it rotates", async () => {
  const auth = createAuth();

  const first = await auth.signTrainingToken(subject);
  const second = await auth.signTrainingToken(subject);

  const kid = (token: string) => decode(token.split(".")[0] ?? "").kid;
  expect(kid(second.token)).toBe(kid(first.token));
  expect(decode(first.token.split(".")[1] ?? "").jti).not.toBe(
    decode(second.token.split(".")[1] ?? "").jti,
  );
  expect(await jwks(auth)).toHaveLength(1);
});

it("does not serve the plugin's workspace-less session token", async () => {
  const response = await createAuth().handler(
    new Request(`${baseUrl}/api/auth/token`),
  );

  expect(response.status).toBe(404);
});

it("signs a short-lived service token for grad's internal listener", async () => {
  const auth = createAuth();
  const consoleToken = await auth.signTrainingToken(subject);

  const { token, expiresAt } = await auth.signServiceToken({
    service: "inference",
    workspaceId: subject.workspaceId,
    scopes: ["artifacts:pin"],
  });

  const [header = "", payload = ""] = token.split(".");
  const claims = decode(payload);
  expect(decode(header)).toMatchObject({
    alg: "ES256",
    kid: decode(consoleToken.token.split(".")[0] ?? "").kid,
  });
  expect(claims).toEqual({
    iss: baseUrl,
    aud: "training",
    sub: "service:inference",
    ws: subject.workspaceId,
    scopes: ["artifacts:pin"],
    jti: expect.any(String),
    iat: expect.any(Number),
    exp: (claims.iat as number) + 300,
  });
  expect(claims).not.toHaveProperty("role");
  expect(expiresAt.getTime()).toBe((claims.exp as number) * 1000);
});

it.each([
  { service: "Inference", scopes: ["artifacts:pin" as const] },
  { service: "inference", scopes: [] },
])("refuses a service token for $service with $scopes", async (input) => {
  await expect(
    createAuth().signServiceToken({
      ...input,
      workspaceId: subject.workspaceId,
    }),
  ).rejects.toThrow();
});
