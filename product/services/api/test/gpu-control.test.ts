import { describe, expect, it, vi } from "vitest";
import { createGpuControlApp } from "../src/gpu-control.js";
import type { AdapterHostingDependencies } from "../src/routes/adapter-hosting.js";

const app = (adapters?: AdapterHostingDependencies) =>
  createGpuControlApp({
    provider: "runpod",
    status: { report: async () => undefined },
    check: async () => ({ postgres: { status: "up" } }),
    ...(adapters ? { adapters } : {}),
  });

describe("private GPU control listener", () => {
  it("does not mount customer or login APIs", async () => {
    for (const path of ["/api/auth/session", "/api/v1/workspaces"])
      expect((await app().request(path)).status).toBe(404);
    expect(await (await app().request("/health/live")).json()).toEqual({
      status: "live",
    });
  });

  it("rejects oversized adapter requests before credential lookup or JSON parsing", async () => {
    const credentials = vi.fn();
    const privateApp = app({
      credentials,
      service: {},
    } as unknown as AdapterHostingDependencies);
    const response = await privateApp.request(
      "/api/internal/v1/adapter-downloads",
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: "x".repeat(1024 * 1024 + 1),
      },
    );
    expect(response.status).toBe(413);
    expect(credentials).not.toHaveBeenCalled();
  });
});
