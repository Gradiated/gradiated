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

  it("uses network authentication for private adapter requests", async () => {
    const credentials = vi.fn(() => {
      throw new Error("Legacy credentials must not be consulted");
    });
    const productionVersions = vi.fn(async () => []);
    const privateApp = app({
      credentials,
      service: { productionVersions },
    } as unknown as AdapterHostingDependencies);
    const response = await privateApp.request(
      "/api/internal/v1/task-versions/production?base_model_id=z-ai%2Fglm-5.3-flash",
    );
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ data: [] });
    expect(credentials).not.toHaveBeenCalled();
    expect(productionVersions).toHaveBeenCalledWith("z-ai/glm-5.3-flash");
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
