import { describe, expect, it } from "vitest";

import { createApp } from "../src/app.js";

describe("health routes", () => {
  it("reports liveness and a request ID", async () => {
    const response = await createApp().request("/health/live");

    expect(response.status).toBe(200);
    expect(response.headers.get("x-request-id")).toBeTruthy();
    await expect(response.json()).resolves.toEqual({ status: "live" });
  });

  it("fails readiness when a required dependency is down", async () => {
    const app = createApp({
      checkDependencies: async () => ({ postgres: "down", valkey: "up" }),
    });
    const response = await app.request("/health/ready");

    expect(response.status).toBe(503);
    expect(response.headers.get("content-type")).toContain(
      "application/problem+json",
    );
    await expect(response.json()).resolves.toMatchObject({
      code: "not_ready",
      status: 503,
    });
  });
});
