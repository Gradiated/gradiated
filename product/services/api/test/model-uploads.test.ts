import { describe, expect, it, vi } from "vitest";
import { authenticated, createTestApp, user, workspaceId } from "./support.js";

const path = `/api/v1/workspaces/${workspaceId}/model-uploads`;
const id = "0198ae50-94d8-7d4d-a8be-9f9b44b8c774";
const input = {
  task: "triage",
  create_task: true,
  name: "triage-v1",
  base_model_id: "Qwen/Qwen3-0.6B",
  base_model_revision: "a".repeat(40),
  config_size: 200,
  weights_size: 500,
};
const post = (app: ReturnType<typeof createTestApp>, body: unknown) =>
  app.request(path, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });

describe("model upload routes", () => {
  it("requires authentication before issuing upload grants", async () => {
    const create = vi.fn();
    const app = createTestApp({
      services: { training: { uploads: { create, complete: vi.fn() } } },
    });
    expect((await post(app, input)).status).toBe(401);
    expect(create).not.toHaveBeenCalled();
  });
  it("validates upload bounds and prevents caching signed grants", async () => {
    const create = vi.fn(async () => ({
      id,
      config_url: "https://storage.invalid/config",
      weights_url: "https://storage.invalid/weights",
      expires_at: new Date().toISOString(),
    }));
    const app = createTestApp({
      auth: authenticated,
      services: { training: { uploads: { create, complete: vi.fn() } } },
    });
    for (const patch of [
      { weights_size: 536870913 },
      { config_size: 65537 },
      { base_model_revision: "main" },
      { task: ".." },
      { name: "../model" },
    ]) {
      expect((await post(app, { ...input, ...patch })).status).toBe(422);
    }
    expect(create).not.toHaveBeenCalled();
    const response = await post(app, input);
    expect(response.status).toBe(201);
    expect(response.headers.get("cache-control")).toBe("no-store");
    expect(create).toHaveBeenCalledWith(user.id, workspaceId, input);
  });
  it("requires authentication for completion", async () => {
    const complete = vi.fn();
    const app = createTestApp({
      services: { training: { uploads: { complete, create: vi.fn() } } },
    });
    expect(
      (await app.request(`${path}/${id}/version`, { method: "PUT" })).status,
    ).toBe(401);
    expect(complete).not.toHaveBeenCalled();
  });
});
