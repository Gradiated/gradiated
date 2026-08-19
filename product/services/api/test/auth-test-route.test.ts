import { describe, expect, it, vi } from "vitest";

import { createApp } from "../src/app.js";

describe("test magic-link route", () => {
  it("is absent from the production-style app", async () => {
    const handler = vi
      .fn()
      .mockResolvedValue(new Response(null, { status: 418 }));
    const app = createApp({
      auth: {
        handler,
        resolveSession: vi.fn().mockResolvedValue(null),
      },
    });

    const response = await app.request(
      "/api/auth/test/magic-link?email=user@example.com",
    );

    expect(response.status).toBe(418);
    expect(handler).toHaveBeenCalledOnce();
  });

  it("consumes a captured link when the test transport is configured", async () => {
    const takeTestMagicLink = vi
      .fn()
      .mockReturnValueOnce("https://api.example.com/verify")
      .mockReturnValueOnce(null);
    const app = createApp({
      auth: {
        handler: vi.fn(),
        resolveSession: vi.fn().mockResolvedValue(null),
        takeTestMagicLink,
      },
    });

    const first = await app.request(
      "/api/auth/test/magic-link?email=user%40example.com",
    );
    const second = await app.request(
      "/api/auth/test/magic-link?email=user%40example.com",
    );

    expect(first.status).toBe(200);
    await expect(first.json()).resolves.toEqual({
      url: "https://api.example.com/verify",
    });
    expect(second.status).toBe(404);
    expect(takeTestMagicLink).toHaveBeenCalledWith("user@example.com");
  });
});
