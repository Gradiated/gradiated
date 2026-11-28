import type { ControlDatabase } from "@gradiated/control";
import { afterAll, beforeAll, describe, expect, it } from "vitest";

import {
  createTestDatabase,
  type TestDatabase,
} from "../../../packages/control/test/support/postgres.js";
import { createAuthService } from "../src/auth/service.js";

const baseUrl = "https://api.gradiated.test";
const subject = {
  userId: "0198ae50-94d8-7d4d-a8be-9f9b44b8c774",
  organizationId: "0198ae5a-1c62-7b2b-9df2-29d8a5d7d3a4",
  workspaceId: "0198ae5a-2529-7c1a-801b-dc9d5f876a94",
  role: "member" as const,
};

const decode = (part: string) =>
  JSON.parse(Buffer.from(part, "base64url").toString("utf8")) as Record<
    string,
    unknown
  >;

const sessionCookie = (response: Response) =>
  response.headers
    .getSetCookie()
    .map((entry) => entry.split(";")[0])
    .join("; ");

// The JWT plugin over the real drizzle adapter and migrated schema (0039).
describe("training tokens on PostgreSQL", () => {
  let testDatabase: TestDatabase;
  let auth: ReturnType<typeof createAuthService>;
  let code = "";

  beforeAll(async () => {
    testDatabase = await createTestDatabase();
    auth = createAuthService(
      testDatabase.database as unknown as ControlDatabase,
      {
        baseUrl,
        oauth: {
          consoleUrl: "https://console.gradiated.test",
          mcpResource: "https://mcp.gradiated.test/mcp",
        },
        secret: "local-only-not-secret-change-in-production-0001",
        trustedOrigins: [baseUrl],
        onUserCreated: async () => undefined,
        sendMagicLink: async () => undefined,
        sendOtp: async (message) => {
          code = message.code;
        },
      },
    );
  });

  afterAll(() => testDatabase.dispose());

  const post = (path: string, body: unknown) =>
    auth.handler(
      new Request(`${baseUrl}/api/auth${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Origin: baseUrl },
        body: JSON.stringify(body),
      }),
    );

  const signIn = async (email: string) => {
    await post("/email-otp/send-verification-otp", { email, type: "sign-in" });
    const response = await post("/sign-in/email-otp", {
      email,
      otp: code,
      name: "Test user",
    });
    expect(response.status).toBe(200);

    return sessionCookie(response);
  };

  const getSession = (cookie: string) =>
    auth.handler(
      new Request(`${baseUrl}/api/auth/get-session`, {
        headers: { Cookie: cookie },
      }),
    );

  it("stores one encrypted ES256 key and publishes only its public half", async () => {
    const { token } = await auth.signTrainingToken(subject);
    await auth.signServiceToken({
      service: "inference",
      workspaceId: subject.workspaceId,
      scopes: ["artifacts:pin"],
    });

    const { rows } = await testDatabase.pool.query<{
      id: string;
      private_key: string;
      alg: string;
      expires_at: Date;
    }>("select id, private_key, alg, expires_at from jwks");
    expect(rows).toHaveLength(1);
    const [key] = rows;
    expect(decode(token.split(".")[0] ?? "")).toMatchObject({
      alg: "ES256",
      kid: key!.id,
    });
    expect(key!.alg).toBe("ES256");
    expect(key!.private_key).not.toMatch(/"d"/);
    expect(key!.expires_at.getTime() - Date.now()).toBeGreaterThan(
      89 * 24 * 3_600_000,
    );

    const response = await auth.handler(
      new Request(`${baseUrl}/api/auth/jwks`),
    );
    const { keys } = (await response.json()) as {
      keys: Record<string, unknown>[];
    };
    expect(keys).toEqual([
      expect.objectContaining({ kid: key!.id, kty: "EC", crv: "P-256" }),
    ]);
    expect(keys[0]).not.toHaveProperty("d");
  });

  it("keeps sessions working, without a JWT header, when signing fails", async () => {
    const cookie = await signIn("member@example.test");
    await testDatabase.pool.query("alter table jwks rename to jwks_gone");

    try {
      await expect(auth.signTrainingToken(subject)).rejects.toThrow();

      const session = await getSession(cookie);
      expect(session.status).toBe(200);
      expect(await session.json()).toMatchObject({
        user: { email: "member@example.test" },
      });
      expect(session.headers.get("set-auth-jwt")).toBeNull();
      await signIn("second@example.test");
    } finally {
      await testDatabase.pool.query("alter table jwks_gone rename to jwks");
    }
  });
});
