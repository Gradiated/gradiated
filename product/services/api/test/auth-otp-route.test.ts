import { describe, expect, it, vi } from "vitest";

import { createApp } from "../src/app.js";

describe("test OTP route", () => {
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
      "/api/auth/test/otp?email=user@example.com",
    );

    expect(response.status).toBe(418);
    expect(handler).toHaveBeenCalledOnce();
  });

  it("consumes a captured code when the test transport is configured", async () => {
    const takeTestOtp = vi
      .fn()
      .mockReturnValueOnce("841902")
      .mockReturnValueOnce(null);
    const app = createApp({
      auth: {
        handler: vi.fn(),
        resolveSession: vi.fn().mockResolvedValue(null),
        takeTestOtp,
      },
    });

    const first = await app.request(
      "/api/auth/test/otp?email=user%40example.com",
    );
    const second = await app.request(
      "/api/auth/test/otp?email=user%40example.com",
    );

    expect(first.status).toBe(200);
    await expect(first.json()).resolves.toEqual({ code: "841902" });
    expect(second.status).toBe(404);
    expect(takeTestOtp).toHaveBeenCalledWith("user@example.com");
  });
});
