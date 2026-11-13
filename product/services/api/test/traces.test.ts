import { describe, expect, it, vi } from "vitest";
import {
  authenticated,
  createTestApp,
  organizationId,
  workspaceId,
} from "./support.js";
const path = `/api/v1/workspaces/${workspaceId}`;
describe("trace routes", () => {
  it("requires a session before calling content services", async () => {
    const list = vi.fn();
    const app = createTestApp({ services: { traces: { list } } });
    expect((await app.request(`${path}/generations?task_id=test`)).status).toBe(
      401,
    );
    expect(list).not.toHaveBeenCalled();
  });
  it("does not cache generation content and passes the authenticated scope", async () => {
    const list = vi.fn(async () => ({ data: [], next_cursor: null }));
    const app = createTestApp({
      auth: authenticated,
      services: { traces: { list } },
    });
    const response = await app.request(`${path}/generations?task_id=test`);
    expect(response.status).toBe(200);
    expect(response.headers.get("cache-control")).toBe("no-store");
    expect(list).toHaveBeenCalledWith(expect.any(String), workspaceId, {
      task: "test",
    });
  });
  it("rejects mixing task capture filters with hosted-log filters", async () => {
    const list = vi.fn();
    const app = createTestApp({
      auth: authenticated,
      services: { traces: { list } },
    });
    for (const query of [
      "task_id=",
      "task_id=test&model=example",
      "task_id=test&from=2026-09-01T00:00:00.000Z&to=2026-09-02T00:00:00.000Z",
    ]) {
      expect((await app.request(`${path}/generations?${query}`)).status).toBe(
        422,
      );
    }
    expect(list).not.toHaveBeenCalled();
  });
  it("reads a generation by ID and content reference", async () => {
    const content = vi.fn(async () => ({
      generation_id: workspaceId,
      raw: null,
      canonical: null,
    }));
    const app = createTestApp({
      auth: authenticated,
      services: { traces: { content } },
    });
    const response = await app.request(
      `${path}/generations/${workspaceId}?content_ref=ref`,
    );
    expect(response.status).toBe(200);
    expect(content).toHaveBeenCalledWith(
      expect.any(String),
      workspaceId,
      workspaceId,
      { content_ref: "ref" },
    );
  });
  it("reads a generation by ID and task name, and needs exactly one of them", async () => {
    const content = vi.fn(async () => ({
      generation_id: workspaceId,
      raw: null,
      canonical: null,
    }));
    const app = createTestApp({
      auth: authenticated,
      services: { traces: { content } },
    });
    const generation = `${path}/generations/${workspaceId}`;

    expect((await app.request(`${generation}?task_id=support`)).status).toBe(
      200,
    );
    expect(content).toHaveBeenCalledWith(
      expect.any(String),
      workspaceId,
      workspaceId,
      { task: "support" },
    );
    for (const query of ["", "?content_ref=ref&task_id=support"])
      expect((await app.request(`${generation}${query}`)).status).toBe(422);
  });
  it("does not expose the removed workspace discovery and data routes", async () => {
    const app = createTestApp({ auth: authenticated });
    for (const endpoint of [
      "trace-tasks",
      "trace-generations?task=test",
      "tasks/test/data",
    ]) {
      expect((await app.request(`${path}/${endpoint}`)).status).toBe(404);
    }
  });
});
