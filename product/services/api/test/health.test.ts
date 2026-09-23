import { describe, expect, it } from "vitest";

import { createTestApp, dependencyDown, dependencyUp } from "./support.js";

describe("health routes", () => {
  it("reports liveness and a request ID", async () => {
    const response = await createTestApp().request("/health/live");

    expect(response.status).toBe(200);
    expect(response.headers.get("x-request-id")).toBeTruthy();
    await expect(response.json()).resolves.toEqual({ status: "live" });
  });

  it("fails readiness when a required dependency is down", async () => {
    const app = createTestApp({
      checkDependencies: async () => ({
        postgres: dependencyDown,
        valkey: dependencyUp,
      }),
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

  it("reports readiness with every dependency check", async () => {
    const app = createTestApp({
      checkDependencies: async () => ({
        postgres: dependencyUp,
        valkey: dependencyUp,
      }),
    });

    const response = await app.request("/health/ready");

    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({
      status: "ready",
      checks: { postgres: "up", valkey: "up" },
    });
  });
});
