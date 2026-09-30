import { TrainingRunEventPayloadSchema } from "@gradiated/contracts";
import { eq } from "drizzle-orm";
import { v7 as uuidv7 } from "uuid";
import {
  afterAll,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";

import { createCatalogService } from "../src/catalog/service.js";
import {
  tasks,
  workspaces,
  taskVersions,
  trainingRunEvents,
  trainingRuns,
} from "../src/db/schema/index.js";
import { traceTaskKey } from "../src/traces/content.js";
import { createTrainingService } from "../src/training/service.js";
import { createMemoryContentStore } from "./support/content-store.js";
import { modelInput, seedMember } from "./support/fixtures.js";
import { createTestDatabase, type TestDatabase } from "./support/postgres.js";

const sha = "a".repeat(64);

describe("training service", () => {
  let db: TestDatabase;
  let objects: Map<string, Buffer>;
  let store: ReturnType<typeof createMemoryContentStore>;
  let baseModelId: string;

  beforeAll(async () => {
    db = await createTestDatabase();
    const model = modelInput();
    await createCatalogService(db.database).upsertModel(model);
    baseModelId = model.id;
  });
  afterAll(() => db.dispose());
  beforeEach(() => {
    objects = new Map();
    store = createMemoryContentStore(objects);
  });

  const service = () => createTrainingService(db.database, store);

  const captureTrace = (workspaceId: string, task: string) => {
    const key = `v1/ws=${workspaceId}/task=${traceTaskKey(task)}/dt=2026-09-29/hr=10/replica-batch.manifest.json`;
    objects.set(
      key,
      Buffer.from(
        JSON.stringify({
          schema: "gradiated.generation-content-manifest/1",
          generations: [
            {
              workspace_id: workspaceId,
              generation_id: uuidv7(),
              task,
              trace_id: null,
              model: "openai/gpt-5",
              source: "relay",
              trainable: false,
              started_at: "2026-09-29T10:00:00.000Z",
              completed_at: null,
              usage: null,
              retention_days: 30,
              offset: 0,
              length: 1,
            },
          ],
        }),
      ),
    );
  };

  const seedTask = async (workspaceId: string, name = "support-triage") => {
    const [task] = await db.database
      .insert(tasks)
      .values({ id: uuidv7(), workspaceId, name })
      .returning();
    return task!;
  };

  const seedRun = async (taskId: string, finished = true) => {
    const [run] = await db.database
      .insert(trainingRuns)
      .values({
        id: uuidv7(),
        taskId,
        trigger: "automation",
        stage: finished ? "succeeded" : "training",
        baseModelId,
        inputCutoff: new Date(),
        finishedAt: finished ? new Date() : null,
      })
      .returning();
    return run!;
  };

  const seedVersion = async (
    task: { id: string; workspaceId: string },
    status: "available" | "unavailable" = "available",
  ) => {
    const run = await seedRun(task.id);
    const [version] = await db.database
      .insert(taskVersions)
      .values({
        id: uuidv7(),
        workspaceId: task.workspaceId,
        taskId: task.id,
        trainingRunId: run.id,
        name: `support-triage-${run.id}`,
        baseModelId,
        adapter: {
          format: "peft_lora",
          artifact_uri: "s3://bucket/adapter",
          sha256: sha,
          size_bytes: 1,
          rank: 16,
        },
        status,
      })
      .returning();
    return { run, version: version! };
  };

  it("includes only the latest run per task in workspace task summaries", async () => {
    const owner = await seedMember(db.database, { role: "owner" });
    const other = await seedMember(db.database, { role: "owner" });
    const task = await seedTask(owner.workspaceId);
    const empty = await seedTask(owner.workspaceId, "empty");
    const foreign = await seedTask(other.workspaceId);
    const { run, version } = await seedVersion(task);
    await seedVersion(foreign);
    expect(
      (await service().listTasks(owner.userId, owner.workspaceId)).find(
        (row) => row.id === task.id,
      )?.latestRun,
    ).toMatchObject({
      id: run.id,
      versionId: version.id,
      versionName: version.name,
    });
    const latest = await seedRun(task.id, false);
    const rows = await service().listTasks(owner.userId, owner.workspaceId);
    expect(rows).toHaveLength(2);
    expect(rows.find((row) => row.id === empty.id)?.latestRun).toBeNull();
    expect(rows.find((row) => row.id === task.id)?.latestRun).toMatchObject({
      id: latest.id,
      stage: "training",
      versionId: null,
      evaluation: null,
    });
  });

  it("authorizes adapter downloads by workspace and task, independently of serving status", async () => {
    const owner = await seedMember(db.database, { role: "owner" });
    const outsider = await seedMember(db.database, { role: "owner" });
    const task = await seedTask(owner.workspaceId);
    const otherTask = await seedTask(owner.workspaceId, "another-task");
    const { version } = await seedVersion(task, "unavailable");
    const sign = vi.fn(async () => ({
      url: "https://storage.example/adapter",
      expires_at: new Date().toISOString(),
    }));
    const training = createTrainingService(db.database, store, { sign });
    await training.downloadAdapter(
      owner.userId,
      owner.workspaceId,
      task.name,
      version.id,
    );
    expect(sign).toHaveBeenCalledWith(
      version.adapter.artifact_uri,
      version.trainingRunId,
      version.adapter.size_bytes,
      version.adapter.sha256,
    );
    sign.mockClear();
    await expect(
      training.downloadAdapter(
        outsider.userId,
        owner.workspaceId,
        task.name,
        version.id,
      ),
    ).rejects.toThrow();
    await expect(
      training.downloadAdapter(
        owner.userId,
        owner.workspaceId,
        otherTask.name,
        version.id,
      ),
    ).rejects.toThrow();
    await expect(
      training.downloadAdapter(
        owner.userId,
        owner.workspaceId,
        task.name,
        uuidv7(),
      ),
    ).rejects.toThrow();
    await db.database
      .update(workspaces)
      .set({ archivedAt: new Date() })
      .where(eq(workspaces.id, owner.workspaceId));
    await expect(
      training.downloadAdapter(
        owner.userId,
        owner.workspaceId,
        task.name,
        version.id,
      ),
    ).rejects.toThrow();
    expect(sign).not.toHaveBeenCalled();
  });

  it("rejects all training reads from archived workspaces before accessing traces", async () => {
    const owner = await seedMember(db.database, { role: "owner" });
    const task = await seedTask(owner.workspaceId);
    const run = await seedRun(task.id);
    await db.database
      .update(workspaces)
      .set({ archivedAt: new Date() })
      .where(eq(workspaces.id, owner.workspaceId));
    const api = service();
    for (const read of [
      () => api.listTasks(owner.userId, owner.workspaceId),
      () => api.getTask(owner.userId, owner.workspaceId, task.name),
      () => api.listRuns(owner.userId, owner.workspaceId, { task_id: task.id }),
      () => api.getRun(owner.userId, owner.workspaceId, run.id),
      () =>
        api.listRunEvents(owner.userId, owner.workspaceId, run.id, {
          limit: 10,
        }),
      () => api.listVersions(owner.userId, owner.workspaceId, task.name),
    ])
      await expect(read()).rejects.toMatchObject({ code: "not_found" });
    expect(store.list).not.toHaveBeenCalled();
    expect(store.read).not.toHaveBeenCalled();
  });

  it("rejects versions whose workspace or run belongs to another task", async () => {
    const owner = await seedMember(db.database, { role: "owner" });
    const other = await seedMember(db.database, { role: "owner" });
    const task = await seedTask(owner.workspaceId);
    const otherTask = await seedTask(other.workspaceId);
    const { version } = await seedVersion(task);
    const ownRun = await seedRun(task.id);
    const otherRun = await seedRun(otherTask.id);
    for (const fields of [
      { workspaceId: other.workspaceId, trainingRunId: ownRun.id },
      { workspaceId: owner.workspaceId, trainingRunId: otherRun.id },
    ])
      await expect(
        db.database
          .insert(taskVersions)
          .values({ ...version, id: uuidv7(), name: uuidv7(), ...fields }),
      ).rejects.toMatchObject({ cause: { code: "23503" } });
  });

  it("prevents direct persistence of dot-segment labels", async () => {
    const owner = await seedMember(db.database, { role: "owner" });
    for (const name of [".", ".."])
      await expect(seedTask(owner.workspaceId, name)).rejects.toMatchObject({
        cause: { code: "23514" },
      });
  });

  describe("listTasks", () => {
    it("reads persisted tasks without consulting or mutating trace storage", async () => {
      const owner = await seedMember(db.database, { role: "member" });
      const other = await seedMember(db.database, { role: "member" });
      await seedTask(owner.workspaceId, "support-triage");
      await seedTask(owner.workspaceId, "Billing Questions");
      await seedTask(other.workspaceId, "elsewhere");
      captureTrace(owner.workspaceId, "unregistered-trace-only-task");
      store.list.mockRejectedValue(new Error("storage unavailable"));
      store.read.mockRejectedValue(new Error("storage unavailable"));

      const first = await service().listTasks(owner.userId, owner.workspaceId);
      const second = await service().listTasks(owner.userId, owner.workspaceId);
      expect(first.map((task) => task.name)).toEqual([
        "Billing Questions",
        "support-triage",
      ]);
      expect(second).toEqual(first);
      expect(store.list).not.toHaveBeenCalled();
      expect(store.read).not.toHaveBeenCalled();
    });

    it("hides workspaces the user is not a member of", async () => {
      const owner = await seedMember(db.database, { role: "owner" });
      const outsider = await seedMember(db.database, { role: "owner" });

      await expect(
        service().listTasks(outsider.userId, owner.workspaceId),
      ).rejects.toMatchObject({ code: "not_found" });
    });
  });

  describe("updateTask", () => {
    it("rejects an unavailable base model", async () => {
      const owner = await seedMember(db.database, { role: "owner" });
      await seedTask(owner.workspaceId);
      const unavailable = modelInput({ status: "unavailable" });
      await createCatalogService(db.database).upsertModel(unavailable);
      await expect(
        service().updateTask(
          owner.userId,
          owner.workspaceId,
          "support-triage",
          { base_model_id: unavailable.id },
        ),
      ).rejects.toMatchObject({ code: "unavailable" });
    });
    it("changes the base and comparison models", async () => {
      const owner = await seedMember(db.database, { role: "owner" });
      await seedTask(owner.workspaceId);

      const task = await service().updateTask(
        owner.userId,
        owner.workspaceId,
        "support-triage",
        { base_model_id: baseModelId, comparison_model_id: "openai/gpt-5" },
      );

      expect(task).toMatchObject({
        baseModelId,
        comparisonModelId: "openai/gpt-5",
      });
    });

    it.each([
      ["a member", "member", { comparison_model_id: "x" }, "forbidden"],
      [
        "an unknown base model",
        "owner",
        { base_model_id: "nope" },
        "not_found",
      ],
    ] as const)("rejects %s", async (_, role, input, code) => {
      const scope = await seedMember(db.database, { role });
      await seedTask(scope.workspaceId);

      await expect(
        service().updateTask(
          scope.userId,
          scope.workspaceId,
          "support-triage",
          input,
        ),
      ).rejects.toMatchObject({ code });
    });
  });

  describe("runs", () => {
    it("lists a task's runs newest first with their version", async () => {
      const owner = await seedMember(db.database, { role: "member" });
      const task = await seedTask(owner.workspaceId);
      const { run } = await seedVersion(task);
      const active = await seedRun(task.id, false);

      const runs = await service().listRuns(owner.userId, owner.workspaceId, {
        task_id: task.id,
      });

      expect(
        runs.map(({ id, versionId, task }) => ({ id, versionId, task })),
      ).toEqual([
        { id: active.id, versionId: null, task: "support-triage" },
        { id: run.id, versionId: expect.any(String), task: "support-triage" },
      ]);
    });

    it("lists workspace runs with an optional task ID filter without leaking other workspaces", async () => {
      const owner = await seedMember(db.database, { role: "member" });
      const other = await seedMember(db.database, { role: "member" });
      const first = await seedTask(owner.workspaceId, "first");
      const second = await seedTask(owner.workspaceId, "second");
      const foreign = await seedTask(other.workspaceId);
      const a = await seedRun(first.id);
      const b = await seedRun(second.id);
      await seedRun(foreign.id);
      expect(
        (await service().listRuns(owner.userId, owner.workspaceId))
          .map((run) => run.id)
          .sort(),
      ).toEqual([a.id, b.id].sort());
      expect(
        (
          await service().listRuns(owner.userId, owner.workspaceId, {
            task_id: first.id,
          })
        ).map((run) => run.id),
      ).toEqual([a.id]);
      for (const task_id of [foreign.id, uuidv7()])
        expect(
          await service().listRuns(owner.userId, owner.workspaceId, {
            task_id,
          }),
        ).toEqual([]);
    });

    it("allows one unfinished run per task", async () => {
      const owner = await seedMember(db.database, { role: "owner" });
      const task = await seedTask(owner.workspaceId);
      await seedRun(task.id, false);

      await expect(seedRun(task.id, false)).rejects.toThrow();
    });

    it("persists optional progress and method-specific validation measurements", async () => {
      const owner = await seedMember(db.database, { role: "member" });
      const task = await seedTask(owner.workspaceId);
      const run = await seedRun(task.id);
      const progress = {
        type: "trainer_progress" as const,
        step: 10,
        train_loss: 0.7,
        metrics: { "reward/mean": -0.2, "custom/entropy": 0.4 },
      };
      const validation = {
        type: "trainer_observation" as const,
        step: 10,
        name: "validation_completed",
        message: "Validation completed",
        metrics: { validation_loss: 0.8, accuracy: 0.9 },
      };
      await db.database.insert(trainingRunEvents).values(
        [progress, validation].map((payload) => ({
          runId: run.id,
          at: new Date(),
          source: "trainer",
          attempt: 1,
          payload,
        })),
      );
      const events = await service().listRunEvents(
        owner.userId,
        owner.workspaceId,
        run.id,
        { limit: 10 },
      );
      expect(
        events.map((event) =>
          TrainingRunEventPayloadSchema.parse(event.payload),
        ),
      ).toEqual([progress, validation]);
    });

    it("pages a run's events in order", async () => {
      const owner = await seedMember(db.database, { role: "member" });
      const task = await seedTask(owner.workspaceId);
      const run = await seedRun(task.id);
      await db.database.insert(trainingRunEvents).values(
        (["queued", "building_dataset", "training"] as const).map((stage) => ({
          runId: run.id,
          at: new Date(),
          source: "worker" as const,
          attempt: 1,
          payload: { type: "stage_entered" as const, stage },
        })),
      );

      const first = await service().listRunEvents(
        owner.userId,
        owner.workspaceId,
        run.id,
        { limit: 2 },
      );
      const rest = await service().listRunEvents(
        owner.userId,
        owner.workspaceId,
        run.id,
        { after: first.at(-1)!.id, limit: 2 },
      );

      expect([...first, ...rest].map((event) => event.payload)).toEqual([
        { type: "stage_entered", stage: "queued" },
        { type: "stage_entered", stage: "building_dataset" },
        { type: "stage_entered", stage: "training" },
      ]);
    });

    it("hides runs from other workspaces", async () => {
      const owner = await seedMember(db.database, { role: "owner" });
      const other = await seedMember(db.database, { role: "owner" });
      const run = await seedRun((await seedTask(other.workspaceId)).id);

      await expect(
        service().getRun(owner.userId, owner.workspaceId, run.id),
      ).rejects.toMatchObject({ code: "not_found" });
    });
  });

  describe("promote", () => {
    it("points the task's production at an available version", async () => {
      const owner = await seedMember(db.database, { role: "owner" });
      const task = await seedTask(owner.workspaceId);
      const { version } = await seedVersion(task);

      const promoted = await service().promote(
        owner.userId,
        owner.workspaceId,
        "support-triage",
        version.id,
      );

      expect(promoted.productionVersionId).toBe(version.id);
    });

    it.each([
      ["an unavailable version", "owner", "unavailable", false, "unavailable"],
      ["another task's version", "owner", "available", true, "not_found"],
      ["a member", "member", "available", false, "forbidden"],
    ] as const)("rejects %s", async (_, role, status, otherTask, code) => {
      const scope = await seedMember(db.database, { role });
      const task = await seedTask(scope.workspaceId);
      const owner = otherTask
        ? await seedTask(scope.workspaceId, "another")
        : task;
      const { version } = await seedVersion(owner, status);

      await expect(
        service().promote(
          scope.userId,
          scope.workspaceId,
          "support-triage",
          version.id,
        ),
      ).rejects.toMatchObject({ code });
    });
  });
});
