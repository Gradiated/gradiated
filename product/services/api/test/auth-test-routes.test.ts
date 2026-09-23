import { describe, expect, it, vi } from "vitest";

import { anonymous, createTestApp } from "./support.js";

const routes = [
  {
    path: "/api/auth/test/magic-link",
    take: "takeMagicLink",
    body: { url: "https://api.example.com/verify" },
    value: "https://api.example.com/verify",
    missing: "Link not found.",
  },
  {
    path: "/api/auth/test/otp",
    take: "takeOtp",
    body: { code: "841902" },
    value: "841902",
    missing: "Code not found.",
  },
] as const;

describe("auth test mailbox routes", () => {
  it.each(routes)(
    "leaves $path to the auth handler without a mailbox",
    async ({ path }) => {
      const handler = vi.fn(async () => new Response(null, { status: 418 }));
      const app = createTestApp({ auth: { ...anonymous, handler } });

      const response = await app.request(`${path}?email=user@example.com`);

      expect(response.status).toBe(418);
      expect(handler).toHaveBeenCalledOnce();
    },
  );

  it.each(routes)(
    "consumes a captured message once from $path",
    async ({ path, take, body, value, missing }) => {
      const taken = vi
        .fn()
        .mockReturnValueOnce(value)
        .mockReturnValueOnce(null);
      const app = createTestApp({
        authTestMailbox: {
          takeMagicLink: take === "takeMagicLink" ? taken : () => null,
          takeOtp: take === "takeOtp" ? taken : () => null,
        },
      });

      const first = await app.request(`${path}?email=user%40example.com`);
      const second = await app.request(`${path}?email=user%40example.com`);

      expect(first.status).toBe(200);
      await expect(first.json()).resolves.toEqual(body);
      expect(second.status).toBe(404);
      await expect(second.json()).resolves.toEqual({ error: missing });
      expect(taken).toHaveBeenCalledWith("user@example.com");
    },
  );

  it.each(routes)("requires an email address on $path", async ({ path }) => {
    const app = createTestApp({
      authTestMailbox: { takeMagicLink: () => null, takeOtp: () => null },
    });

    const response = await app.request(path);

    expect(response.status).toBe(400);
    await expect(response.json()).resolves.toEqual({
      error: "Email is required.",
    });
  });
});
