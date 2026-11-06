import { afterEach, describe, expect, it, vi } from "vitest";

import { createTestApp, organizationId } from "./support.js";

const ip = "192.0.2.1";
const signup = {
  email: "founder@example.com",
  companySize: "11-50",
  monthlyTokenSpendUsd: "2,500",
  motivation: "Lower inference costs.",
};
const signupRequest = (app: ReturnType<typeof createTestApp>, forwarded = ip) =>
  app.request("/api/v1/waitlist", {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "x-forwarded-for": forwarded,
    },
    body: JSON.stringify(signup),
  });

afterEach(() => vi.useRealTimers());

describe("API request limits", () => {
  it("rate limits requests per IP and permits another client", async () => {
    const app = createTestApp();
    const request = (address: string) =>
      app.request("/api/not-found", {
        headers: { "x-forwarded-for": address },
      });

    for (let i = 0; i < 300; i++) {
      expect((await request(ip)).status).toBe(404);
    }

    const response = await request(ip);
    expect(response.status).toBe(429);
    expect(Number(response.headers.get("retry-after"))).toBeGreaterThan(0);
    expect((await response.json()).code).toBe("rate_limited");
    expect((await request("192.0.2.2")).status).toBe(404);
  });

  it("limits waitlist writes and email sends, ignores spoofed XFF prefixes, and resets", async () => {
    vi.useFakeTimers();
    const join = vi.fn(async () => ({ created: true, email: signup.email }));
    const sendWaitlistWelcome = vi.fn(async () => {});
    const app = createTestApp({
      services: { waitlist: { join } },
      sendWaitlistWelcome,
    });

    for (let i = 0; i < 10; i++) {
      expect((await signupRequest(app, `198.51.100.${i}, ${ip}`)).status).toBe(
        200,
      );
    }

    expect((await signupRequest(app, `203.0.113.1, ${ip}`)).status).toBe(429);
    expect(join).toHaveBeenCalledTimes(10);
    expect(sendWaitlistWelcome).toHaveBeenCalledTimes(10);
    await vi.advanceTimersByTimeAsync(60_001);
    expect((await signupRequest(app)).status).toBe(200);
  });

  it("keeps health checks and Stripe webhooks outside exhausted client quotas", async () => {
    const handleWebhook = vi.fn(async () => {});
    const app = createTestApp({
      services: { billingPayments: { handleWebhook } },
    });

    for (let i = 0; i < 301; i++) {
      await app.request("/api/not-found", {
        headers: { "x-forwarded-for": ip },
      });
    }

    expect((await app.request("/health/live")).status).toBe(200);
    const response = await app.request("/api/webhooks/stripe", {
      method: "POST",
      headers: { "x-forwarded-for": ip, "stripe-signature": "test" },
      body: '{ "test": true }',
    });
    expect(response.status).toBe(200);
    expect(handleWebhook).toHaveBeenCalledWith({
      payload: '{ "test": true }',
      signature: "test",
    });
  });

  it.each([
    { method: "GET", path: "nda-documents/test-document", limit: 60 },
    { method: "POST", path: "nda-documents", limit: 60 },
    {
      method: "POST",
      path: "nda-documents/test-document/signing-sessions",
      limit: 5,
    },
    { method: "POST", path: "slack-invitations", limit: 5 },
    { method: "GET", path: "engineer-onboarding", limit: 60 },
    { method: "POST", path: "engineer-onboarding/submission", limit: 5 },
    { method: "GET", path: "github-installations", limit: 30 },
  ])(
    "limits engineer onboarding route $method $path per IP",
    async ({ method, path, limit }) => {
      const app = createTestApp();
      const request = (address = ip) =>
        app.request(`/api/v1/organizations/${organizationId}/${path}`, {
          method,
          headers: { "x-forwarded-for": address },
        });

      for (let i = 0; i < limit; i++)
        expect((await request()).status).not.toBe(429);

      expect((await request()).status).toBe(429);
      expect((await request("192.0.2.2")).status).not.toBe(429);
    },
  );

  it.each([false, true])(
    "rejects oversized bodies before waitlist service work (declared length: %s)",
    async (declaredLength) => {
      const join = vi.fn();
      const app = createTestApp({ services: { waitlist: { join } } });
      const body = " ".repeat(1024 * 1024) + JSON.stringify(signup);
      const response = await app.request("/api/v1/waitlist", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          ...(declaredLength ? { "content-length": String(body.length) } : {}),
        },
        body,
      });
      expect(response.status).toBe(413);
      expect(join).not.toHaveBeenCalled();
    },
  );
});
