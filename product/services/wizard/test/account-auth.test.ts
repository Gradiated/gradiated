import { createServer, type Server } from "node:http";
import type { AddressInfo } from "node:net";
import { betterAuth } from "better-auth";
import { memoryAdapter } from "better-auth/adapters/memory";
import { emailOTP } from "better-auth/plugins";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { resolveAccount } from "../src/account.js";
import * as ui from "../src/ui.js";

vi.mock("../src/ui.js", () => ({
  askText: vi.fn(),
  spinner: () => ({ start: vi.fn(), stop: vi.fn() }),
  note: vi.fn(),
  success: vi.fn(),
  info: vi.fn(),
  fail: (message: string) => {
    throw new Error(message);
  },
}));

let server: Server;
let baseUrl: string;
let auth: {
  handler: (request: Request) => Promise<Response>;
  api: {
    getSession: (input: {
      headers: Headers;
    }) => Promise<{ user: { id: string } } | null>;
  };
};
let code: string;
let deliveries: number;
let keyRequests: number;
let signedInUsers: string[];

beforeEach(async () => {
  vi.clearAllMocks();
  code = "";
  deliveries = 0;
  keyRequests = 0;
  signedInUsers = [];
  server = createServer(async (request, response) => {
    try {
      const headers = new Headers();
      for (const [name, value] of Object.entries(request.headers)) {
        if (value !== undefined)
          headers.set(name, Array.isArray(value) ? value.join(", ") : value);
      }
      if (request.url === "/api/v1/wizard/key") {
        keyRequests++;
        const session = await auth.api.getSession({ headers });
        response.setHeader("content-type", "application/json");
        if (!session || headers.get("origin") !== baseUrl) {
          response
            .writeHead(401)
            .end('{"message":"Missing session or origin"}');
          return;
        }
        signedInUsers.push(session.user.id);
        response.writeHead(201).end(
          JSON.stringify({
            secret: "grad_fixture",
            organization_name: "Personal",
            balance_nano_usd: 0,
          }),
        );
        return;
      }
      let body = "";
      for await (const chunk of request) body += String(chunk);
      const result = await auth.handler(
        new Request(`${baseUrl}${request.url}`, {
          method: request.method!,
          headers,
          ...(body ? { body } : {}),
        }),
      );
      response.statusCode = result.status;
      result.headers.forEach((value, name) => {
        if (name !== "set-cookie") response.setHeader(name, value);
      });
      const cookies = result.headers.getSetCookie();
      if (cookies.length) response.setHeader("set-cookie", cookies);
      response.end(await result.text());
    } catch {
      response.writeHead(500).end('{"message":"Test auth server failed"}');
    }
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  baseUrl = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
  auth = betterAuth({
    baseURL: baseUrl,
    basePath: "/api/auth",
    secret: "test-only-auth-secret-at-least-thirty-two-characters",
    database: memoryAdapter({
      user: [],
      session: [],
      account: [],
      verification: [],
    }),
    // Better Auth disables origin checks under NODE_ENV=test by default.
    // Keep production protection enabled so missing headers cannot slip through.
    advanced: { disableOriginCheck: false, disableCSRFCheck: false },
    plugins: [
      emailOTP({
        expiresIn: 600,
        otpLength: 6,
        storeOTP: "hashed",
        sendVerificationOTP: async (message) => {
          code = message.otp;
          deliveries++;
        },
      }),
    ],
  });
  vi.mocked(ui.askText).mockImplementation(async (prompt) =>
    prompt === "Email:" ? "person@example.com" : code,
  );
});

afterEach(async () => {
  await new Promise<void>((resolve, reject) =>
    server.close((error) => (error ? reject(error) : resolve())),
  );
});

describe("wizard with real Better Auth origin and session checks", () => {
  it("reproduces the reported error before sending an email when Origin is absent", async () => {
    const response = await fetch(
      `${baseUrl}/api/auth/email-otp/send-verification-otp`,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ email: "person@example.com", type: "sign-in" }),
      },
    );
    expect(response.status).toBe(403);
    expect(await response.json()).toMatchObject({
      message: "Missing or null Origin",
    });
    expect(deliveries).toBe(0);
  });

  it("signs up and logs back in through OTP and authenticates key creation", async () => {
    const targets = { apiBaseUrl: `${baseUrl}/`, inferenceBaseUrl: baseUrl };
    expect((await resolveAccount(targets, "signup")).apiKey).toBe(
      "grad_fixture",
    );
    expect((await resolveAccount(targets, "login")).apiKey).toBe(
      "grad_fixture",
    );
    expect(deliveries).toBe(2);
    expect(keyRequests).toBe(2);
    expect(signedInUsers[0]).toBeTruthy();
    expect(signedInUsers[0]).toBe(signedInUsers[1]);
  });
});
