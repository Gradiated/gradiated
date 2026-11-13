import {
  ControlServiceError,
  type TrainingRunRecord,
  TrainingAdmissionError,
} from "@gradiated/control";
import { describe, expect, it, vi } from "vitest";
import {
  authenticated,
  createTestApp,
  organizationId,
  user,
  workspaceId,
} from "./support.js";

const path = `/api/v1/workspaces/${workspaceId}`;
const runId = "0198ae50-94d8-7d4d-a8be-9f9b44b8c774";
const at = new Date("2026-09-29T10:00:00.000Z");

const task = {
  id: runId,
  organizationId,
  workspaceId,
  name: "Billing Questions",
  baseModelId: "gradiated/base",
  comparisonModelId: "openai/gpt-5",
  judgeModelId: "openai/gpt-5" as const,
  productionVersionId: runId,
  trainingSchedule: "0 3 * * MON",
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
  it("returns uncached held-out comparisons only after authentication", async () => {
    const rows = [
      {
        id: "example",
        group: "group",
        judgment: "TIE",
        fine_tuned_first: true,
        fine_tuned: { text: "144", tokens: 3, seconds: 1 },
        comparison: { text: "144", tokens: 3, seconds: 1 },
      },
    ];
    const evaluationResults = vi.fn(async () => rows);
    const url = `${path}/tasks/Billing%20Questions/versions/${runId}/evaluation`;
    const anonymous = createTestApp({
      services: { training: { evaluationResults } },
    });
    expect((await anonymous.request(url)).status).toBe(401);
    expect(evaluationResults).not.toHaveBeenCalled();
    const app = createTestApp({
      auth: authenticated,
      services: { training: { evaluationResults } },
    });
    const response = await app.request(url);
    expect(response.status).toBe(200);
    expect(response.headers.get("cache-control")).toBe("no-store");
    expect(await response.json()).toEqual(rows);
    expect(evaluationResults).toHaveBeenCalledWith(
      user.id,
      workspaceId,
      "Billing Questions",
      runId,
    );
  });

  it("returns uncached adapter links only to authenticated requests", async () => {
    const result = {
      url: "https://storage.example/adapter.tar.gz",
      expires_at: at.toISOString(),
    };
    const downloadAdapter = vi.fn(async () => result);
    const url = `${path}/tasks/Billing%20Questions/versions/${runId}/adapter`;
    const anonymous = createTestApp({
      services: { training: { downloadAdapter } },
    });
    expect((await anonymous.request(url)).status).toBe(401);
    expect(downloadAdapter).not.toHaveBeenCalled();
    const app = createTestApp({
      auth: authenticated,
      services: { training: { downloadAdapter } },
    });
    const response = await app.request(url);
    expect(response.status).toBe(200);
    expect(response.headers.get("Cache-Control")).toBe("no-store");
    expect(await response.json()).toEqual(result);
    expect(downloadAdapter).toHaveBeenCalledWith(
      expect.any(String),
      workspaceId,
      "Billing Questions",
      runId,
    );
  });

  it("serializes task collection run summaries without additional history reads", async () => {
    const latestRun: TrainingRunRecord & { versionName: string } = {
      workflowId: null,
      id: runId,
      task: task.name,
      taskId: task.id,
      trigger: "manual",
      requestedBy: null,
      stage: "succeeded",
      baseModelId: task.baseModelId,
      inputCutoff: at,
      dataset: null,
      evaluation: null,
      versionId: runId,
      versionName: "billing-v1",
      updatedAt: at,
      cancelRequestedAt: null,
      createdAt: at,
      finishedAt: at,
    };
    const listTasks = vi.fn(async () => [
      { ...task, latestRun, latestVersion: null },
      {
        ...task,
        id: "0198ae50-94d8-7d4d-a8be-9f9b44b8c775",
        latestRun: null,
        latestVersion: null,
      },
    ]);
    const app = createTestApp({
      auth: authenticated,
      services: { training: { listTasks } },
    });
    const response = await app.request(`${path}/tasks`);
    expect(response.status).toBe(200);
    const result = await response.json();
    expect(result.data[0].latest_run).toMatchObject({
      id: runId,
      version_name: "billing-v1",
      finished_at: at.toISOString(),
      evaluation: null,
    });
    expect(result.data[1].latest_run).toBeNull();
  });

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
        judge_model_id: "openai/gpt-5",
        production_version_id: runId,
        training_schedule: "0 3 * * MON",
      });
      expect(getTask).toHaveBeenCalledWith(
        expect.any(String),
        workspaceId,
        name,
      );
    },
  );

  it.each(["0 3 1 * *", null])(
    "updates automatic training cron %s",
    async (training_schedule) => {
      const updateTask = vi.fn(async () => ({
        ...task,
        trainingSchedule: training_schedule,
      }));
      const app = createTestApp({
        auth: authenticated,
        services: { training: { updateTask } },
      });
      const response = await app.request(`${path}/tasks/task`, {
        method: "PATCH",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ training_schedule }),
      });

      expect(response.status).toBe(200);
      expect(await response.json()).toMatchObject({ training_schedule });
      expect(updateTask).toHaveBeenCalledWith(
        expect.any(String),
        workspaceId,
        "task",
        { training_schedule },
      );
    },
  );

  it("rejects invalid automatic training cron before updating the task", async () => {
    const updateTask = vi.fn();
    const app = createTestApp({
      auth: authenticated,
      services: { training: { updateTask } },
    });
    const response = await app.request(`${path}/tasks/task`, {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ training_schedule: "0 25 * * *" }),
    });

    expect(response.status).toBe(422);
    expect(updateTask).not.toHaveBeenCalled();
  });

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
      "an empty version",
      `${path}/tasks/t/production`,
      { version_id: "" },
      "PUT",
    ],
  ])("rejects %s", async (_, url, body, method) => {
    const app = createTestApp({ auth: authenticated });

    expect((await request(app, url, body, method)).status).toBe(422);
  });

  it("reads and promotes a version by its name", async () => {
    const getVersion = vi.fn(async () => {
      throw new ControlServiceError("not_found", "The version was not found.");
    });
    const promote = vi.fn(async () => task);
    const app = createTestApp({
      auth: authenticated,
      services: { training: { getVersion, promote } },
    });

    expect((await app.request(`${path}/tasks/t/versions/t-v2`)).status).toBe(
      404,
    );
    expect(getVersion).toHaveBeenCalledWith(
      expect.any(String),
      expect.any(String),
      "t",
      "t-v2",
    );
    expect(
      (
        await request(
          app,
          `${path}/tasks/t/production`,
          { version_id: "t-v2" },
          "PUT",
        )
      ).status,
    ).toBe(200);
    expect(promote).toHaveBeenCalledWith(
      expect.any(String),
      expect.any(String),
      "t",
      "t-v2",
    );
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

it("accepts a manual run and returns the workflow execution ID", async () => {
  const startRun = vi.fn(async () => ({ id: runId }));
  const app = createTestApp({
    auth: authenticated,
    services: { training: { startRun } },
  });
  const response = await app.request(`${path}/training-runs`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ task_id: runId }),
  });
  expect(response.status).toBe(202);
  expect(await response.json()).toEqual({ id: runId });
  expect(startRun).toHaveBeenCalledWith(expect.any(String), workspaceId, runId);
});

it("requests cancellation of the exact run", async () => {
  const cancelRun = vi.fn(async () => {});
  const app = createTestApp({
    auth: authenticated,
    services: { training: { cancelRun } },
  });
  const response = await app.request(`${path}/training-runs/${runId}`, {
    method: "DELETE",
  });
  expect(response.status).toBe(202);
  expect(cancelRun).toHaveBeenCalledWith(
    expect.any(String),
    workspaceId,
    runId,
  );
});

it.each([
  ["already_training", 409],
  ["insufficient_traces", 422],
  ["training_not_configured", 422],
] as const)("returns %i for %s admission", async (code, status) => {
  const startRun = vi.fn(async () => {
    throw new TrainingAdmissionError(code, "Training prerequisite failed.");
  });
  const app = createTestApp({
    auth: authenticated,
    services: { training: { startRun } },
  });
  const response = await app.request(`${path}/training-runs`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ task_id: runId }),
  });
  expect(response.status).toBe(status);
  expect(await response.json()).toMatchObject({
    code,
    detail: "Training prerequisite failed.",
  });
});

it.each([{}, { task_id: "not-a-uuid" }, { run_id: runId }])(
  "rejects creation without a valid task ID: %j",
  async (body) => {
    const startRun = vi.fn();
    const app = createTestApp({
      auth: authenticated,
      services: { training: { startRun } },
    });
    const response = await app.request(`${path}/training-runs`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    });
    expect(response.status).toBe(422);
    expect(startRun).not.toHaveBeenCalled();
  },
);
