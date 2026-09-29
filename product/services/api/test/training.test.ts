import { ControlServiceError } from "@gradiated/control";
import { describe, expect, it, vi } from "vitest";
import { authenticated, createTestApp, workspaceId } from "./support.js";

const path = `/api/v1/workspaces/${workspaceId}`;
const runId = "0198ae50-94d8-7d4d-a8be-9f9b44b8c774";
const at = new Date("2026-09-29T10:00:00.000Z");

const task = {
  id: runId,
  workspaceId,
  name: "Billing Questions",
  baseModelId: "gradiated/base",
  comparisonModelId: "openai/gpt-5",
  productionVersionId: runId,
  createdAt: at,
  updatedAt: at,
};

const request = (
  app: ReturnType<typeof createTestApp>,
  url: string,
  body?: unknown,
  method = "PATCH",
) =>
  app.request(
    url,
    body === undefined
      ? {}
      : {
          method,
          headers: { "content-type": "application/json" },
          body: JSON.stringify(body),
        },
  );

describe("training routes", () => {
  it("requires a session", async () => {
    const listTasks = vi.fn();
    const app = createTestApp({ services: { training: { listTasks } } });

    expect((await app.request(`${path}/tasks`)).status).toBe(401);
    expect(listTasks).not.toHaveBeenCalled();
  });

  it.each(["Billing Questions", "t".repeat(201), "t".repeat(256)])(
    "addresses captured task %s",
    async (name) => {
      const getTask = vi.fn(async () => ({ ...task, name }));
      const app = createTestApp({
        auth: authenticated,
        services: { training: { getTask } },
      });

      const response = await app.request(
        `${path}/tasks/${encodeURIComponent(name)}`,
      );

      expect(await response.json()).toEqual({
        id: task.id,
        name,
        base_model_id: "gradiated/base",
        comparison_model_id: "openai/gpt-5",
        production_version_id: runId,
      });
      expect(getTask).toHaveBeenCalledWith(
        expect.any(String),
        workspaceId,
        name,
      );
    },
  );

  it.each([undefined, runId])(
    "lists training runs with task filter %s",
    async (taskId) => {
      const listRuns = vi.fn(async () => []);
      const app = createTestApp({
        auth: authenticated,
        services: { training: { listRuns } },
      });
      const response = await app.request(
        `${path}/training-runs${taskId ? `?task_id=${taskId}` : ""}`,
      );
      expect(response.status).toBe(200);
      expect(await response.json()).toEqual({ data: [] });
      expect(listRuns).toHaveBeenCalledWith(
        expect.any(String),
        workspaceId,
        taskId ? { task_id: taskId } : {},
      );
    },
  );

  it("rejects malformed task ID filters before calling the service", async () => {
    const listRuns = vi.fn();
    const app = createTestApp({
      auth: authenticated,
      services: { training: { listRuns } },
    });
    expect(
      (await app.request(`${path}/training-runs?task_id=not-a-uuid`)).status,
    ).toBe(422);
    expect(listRuns).not.toHaveBeenCalled();
    expect((await app.request(`${path}/tasks/name/runs`)).status).toBe(404);
  });

  it("maps a missing task to 404", async () => {
    const getTask = vi.fn(async () => {
      throw new ControlServiceError("not_found", "The task was not found.");
    });
    const app = createTestApp({
      auth: authenticated,
      services: { training: { getTask } },
    });

    expect((await app.request(`${path}/tasks/missing`)).status).toBe(404);
  });

  it.each([
    ["an empty task update", `${path}/tasks/t`, {}, "PATCH"],
    ["an unknown task field", `${path}/tasks/t`, { name: "x" }, "PATCH"],
    [
      "a malformed version id",
      `${path}/tasks/t/production`,
      { version_id: "x" },
      "PUT",
    ],
  ])("rejects %s", async (_, url, body, method) => {
    const app = createTestApp({ auth: authenticated });

    expect((await request(app, url, body, method)).status).toBe(422);
  });

  it("returns a cursor only when a page of events is full", async () => {
    const event = (id: number) => ({
      id,
      runId,
      at,
      source: "worker" as const,
      attempt: 1,
      payload: { type: "stage_entered" as const, stage: "queued" as const },
    });
    const listRunEvents = vi
      .fn()
      .mockResolvedValueOnce([event(1), event(2)])
      .mockResolvedValueOnce([event(3)]);
    const app = createTestApp({
      auth: authenticated,
      services: { training: { listRunEvents } },
    });

    const full = await app.request(
      `${path}/training-runs/${runId}/events?limit=2`,
    );
    const last = await app.request(
      `${path}/training-runs/${runId}/events?limit=2&after=2`,
    );

    expect((await full.json()).next_cursor).toBe("2");
    expect((await last.json()).next_cursor).toBeNull();
    expect(listRunEvents).toHaveBeenLastCalledWith(
      expect.any(String),
      workspaceId,
      runId,
      { after: 2, limit: 2 },
    );
  });

  it("marks the production version", async () => {
    const version = (id: string) => ({
      id,
      workspaceId,
      taskId: task.id,
      trainingRunId: runId,
      name: `billing-${id.slice(-4)}`,
      baseModelId: "gradiated/base",
      adapter: {
        format: "peft_lora" as const,
        artifact_uri: "s3://bucket/adapter",
        sha256: "a".repeat(64),
        size_bytes: 1,
        rank: 16,
      },
      status: "available" as const,
      createdAt: at,
      updatedAt: at,
    });
    const listVersions = vi.fn(async () => ({
      task,
      versions: [
        version(runId),
        version("0198ae50-94d8-7d4d-a8be-9f9b44b8c775"),
      ],
    }));
    const app = createTestApp({
      auth: authenticated,
      services: { training: { listVersions } },
    });

    const { data } = await (
      await app.request(`${path}/tasks/t/versions`)
    ).json();

    expect(
      data.map((v: { is_production: boolean }) => v.is_production),
    ).toEqual([true, false]);
  });
});
