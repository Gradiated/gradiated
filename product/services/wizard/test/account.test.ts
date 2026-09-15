import { createServer, type Server } from "node:http";
import type { AddressInfo } from "node:net";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { resolveAccount } from "../src/account.js";
import * as ui from "../src/ui.js";

vi.mock("../src/ui.js", () => ({
  askText: vi.fn(),
  selectOption: vi.fn(),
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
let sessionStatus: number;
let cookies: string[];
let calls: { path: string; body: unknown; cookie: string | undefined }[];

beforeEach(async () => {
  vi.clearAllMocks();
  vi.mocked(ui.askText)
    .mockResolvedValueOnce(" person@example.com ")
    .mockResolvedValueOnce(" 123456 ");
  vi.mocked(ui.selectOption).mockResolvedValue("login");
  calls = [];
  sessionStatus = 200;
  cookies = [
    "better-auth.session_token=fixture-session; Path=/; HttpOnly; SameSite=Lax",
    "better-auth.session_data=fixture-data; Expires=Wed, 16 Sep 2026 00:00:00 GMT; Path=/; HttpOnly",
  ];
  server = createServer(async (request, response) => {
    let raw = "";
    for await (const chunk of request) raw += String(chunk);
    calls.push({
      path: request.url!,
      body: raw ? JSON.parse(raw) : null,
      cookie: request.headers.cookie,
    });
    response.setHeader("content-type", "application/json");
    if (request.url === "/api/auth/email-otp/send-verification-otp") {
      response.end('{"success":true}');
    } else if (request.url === "/api/auth/sign-in/email-otp") {
      response.statusCode = sessionStatus;
      if (cookies.length) response.setHeader("set-cookie", cookies);
      response.end(
        sessionStatus === 200
          ? '{"user":{"id":"fixture-user"}}'
          : '{"message":"Invalid OTP"}',
      );
    } else if (
      request.url === "/api/v1/wizard/key" &&
      request.headers.cookie ===
        "better-auth.session_token=fixture-session; better-auth.session_data=fixture-data"
    ) {
      response.statusCode = 201;
      response.end(
        JSON.stringify({
          secret: "grad_fixture",
          organization_name: "Personal",
          balance_nano_usd: 5_000_000_000,
        }),
      );
    } else {
      response.statusCode = 401;
      response.end('{"message":"Missing session"}');
    }
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  baseUrl = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
});

afterEach(async () => {
  await new Promise<void>((resolve, reject) =>
    server.close((error) => (error ? reject(error) : resolve())),
  );
});

describe("account setup", () => {
  it.each(["signup", "login"] as const)(
    "completes %s through the deployed auth routes with a session",
    async (mode) => {
      const account = await resolveAccount(
        { apiBaseUrl: baseUrl, inferenceBaseUrl: baseUrl },
        mode,
      );
      expect(account.apiKey).toBe("grad_fixture");
      expect(account.balanceNanoUsd).toBe(5_000_000_000);
      expect(ui.selectOption).not.toHaveBeenCalled();
      expect(calls).toEqual([
        {
          path: "/api/auth/email-otp/send-verification-otp",
          body: { email: "person@example.com", type: "sign-in" },
          cookie: undefined,
        },
        {
          path: "/api/auth/sign-in/email-otp",
          body: { email: "person@example.com", otp: "123456" },
          cookie: undefined,
        },
        {
          path: "/api/v1/wizard/key",
          body: null,
          cookie:
            "better-auth.session_token=fixture-session; better-auth.session_data=fixture-data",
        },
      ]);
    },
  );

  it("does not mint a key after a rejected code", async () => {
    sessionStatus = 401;
    await expect(
      resolveAccount(
        { apiBaseUrl: baseUrl, inferenceBaseUrl: baseUrl },
        "login",
      ),
    ).rejects.toThrow("code was rejected");
    expect(calls).toHaveLength(2);
  });

  it("reports a missing session before attempting key creation", async () => {
    cookies = [];
    await expect(
      resolveAccount(
        { apiBaseUrl: baseUrl, inferenceBaseUrl: baseUrl },
        "signup",
      ),
    ).rejects.toThrow("session cookie");
    expect(calls).toHaveLength(2);
  });
});
