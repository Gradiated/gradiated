import { randomUUID } from "node:crypto";
import { eq } from "drizzle-orm";
import {
  afterAll,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";
import {
  taskVersions,
  tasks,
  trainingRunEvents,
  trainingRuns,
  workspaces,
} from "../src/db/schema/index.js";
import {
  createTrainingArtifactCleanup,
  deleteArchivedTasks,
} from "../src/training/artifact-cleanup.js";
import type { ContentStore } from "../src/traces/storage.js";
import { createMemoryContentStore } from "./support/content-store.js";
import { createTestDatabase, type TestDatabase } from "./support/postgres.js";
import { seedTrainingTask, trainingAdapter } from "./support/training.js";

const HOUR = 60 * 60 * 1000;

describe("training artifact cleanup", () => {
  let db: TestDatabase;
  let objects: Map<string, Buffer>;
  let store: ContentStore;
  let clock: number;
  const now = () => new Date(clock);
  const engine = {
    updateSchedule: vi.fn(async (_taskId: string, _cron: string | null) => {}),
  };

  beforeAll(async () => {
    db = await createTestDatabase();
  });
  afterAll(() => db.dispose());
  beforeEach(() => {
    objects = new Map();
    store = createMemoryContentStore(objects);
    clock = Date.now();
    engine.updateSchedule.mockClear();
  });

  const seedRun = async (finished = true) => {
    const seed = await seedTrainingTask(db.database);
    const runId = randomUUID();
    await db.database.insert(trainingRuns).values({
      id: runId,
      taskId: seed.task.id,
      stage: finished ? "succeeded" : "training",
      trigger: "manual",
      baseModelId: seed.input.baseModelId,
      inputCutoff: new Date(seed.input.inputCutoff),
      createdAt: now(),
      finishedAt: finished ? now() : null,
    });
    await db.database.insert(trainingRunEvents).values({
      runId,
      source: "worker",
      attempt: 1,
      at: now(),
      payload: { type: "stage_entered", stage: "training" },
    });
    if (finished)
      await db.database.insert(taskVersions).values({
        id: randomUUID(),
        workspaceId: seed.workspaceId,
        taskId: seed.task.id,
        trainingRunId: runId,
        name: `v-${runId}`,
        baseModelId: seed.input.baseModelId,
        adapter: trainingAdapter,
        status: "available",
      });
    for (const key of [
      "run-manifest.json",
      "dataset/v1/train.jsonl",
      "evaluation/pairs/abc.json",
      "output/1/adapter.tar.gz",
    ])
      objects.set(`runs/${runId}/${key}`, Buffer.from("synthetic"));
    return { ...seed, runId };
  };

  const archive = (workspaceId: string) =>
    db.database
      .update(workspaces)
      .set({ archivedAt: now() })
      .where(eq(workspaces.id, workspaceId));

  const drain = async (cleanup: () => Promise<void>) => {
    for (let pass = 0; pass < 20; pass++) await cleanup();
    await deleteArchivedTasks(db.database, engine);
  };

  const rows = async (taskId: string, runId: string) => ({
    tasks: await db.database.select().from(tasks).where(eq(tasks.id, taskId)),
    runs: await db.database
      .select()
      .from(trainingRuns)
      .where(eq(trainingRuns.id, runId)),
    events: await db.database
      .select()
      .from(trainingRunEvents)
      .where(eq(trainingRunEvents.runId, runId)),
    versions: await db.database
      .select()
      .from(taskVersions)
      .where(eq(taskVersions.trainingRunId, runId)),
  });

  const runObjects = (runId: string) =>
    [...objects.keys()].filter((key) => key.startsWith(`runs/${runId}/`));

  it("deletes the artifacts, rows and schedules of a deleted workspace", async () => {
    const kept = await seedRun();
    const deleted = await seedRun();
    await archive(deleted.workspaceId);
    const cleanup = createTrainingArtifactCleanup(db.database, store, now);

    await drain(cleanup);
    expect(runObjects(deleted.runId)).toHaveLength(4);
    expect(engine.updateSchedule).not.toHaveBeenCalled();

    clock += 3 * HOUR + 1;
    await drain(cleanup);

    expect(runObjects(deleted.runId)).toEqual([]);
    expect(await rows(deleted.task.id, deleted.runId)).toEqual({
      tasks: [],
      runs: [],
      events: [],
      versions: [],
    });
    expect(engine.updateSchedule).toHaveBeenCalledExactlyOnceWith(
      deleted.task.id,
      null,
    );
    expect(runObjects(kept.runId)).toHaveLength(4);
    const live = await rows(kept.task.id, kept.runId);
    expect(live.tasks).toHaveLength(1);
    expect(live.runs).toHaveLength(1);
    expect(live.versions).toHaveLength(1);
  });

  it("keeps the run row until its objects are deleted, then retries", async () => {
    const deleted = await seedRun();
    await archive(deleted.workspaceId);
    clock += 4 * HOUR;
    vi.mocked(store.delete).mockRejectedValueOnce(new Error("S3 outage"));
    const cleanup = createTrainingArtifactCleanup(db.database, store, now);

    await expect(cleanup()).rejects.toThrow("S3 outage");
    expect((await rows(deleted.task.id, deleted.runId)).runs).toHaveLength(1);

    await drain(cleanup);
    expect(objects.size).toBe(0);
    expect((await rows(deleted.task.id, deleted.runId)).runs).toEqual([]);
  });

  it("deletes the schedule of a task with automatic training off, then the task", async () => {
    const deleted = await seedRun();
    await db.database
      .update(tasks)
      .set({ trainingSchedule: null })
      .where(eq(tasks.id, deleted.task.id));
    await archive(deleted.workspaceId);
    clock += 4 * HOUR;
    engine.updateSchedule.mockRejectedValueOnce(new Error("Temporal outage"));
    const cleanup = createTrainingArtifactCleanup(db.database, store, now);

    await expect(drain(cleanup)).rejects.toThrow("Temporal outage");
    expect(objects.size).toBe(0);
    expect((await rows(deleted.task.id, deleted.runId)).tasks).toHaveLength(1);

    await drain(cleanup);
    expect(engine.updateSchedule).toHaveBeenLastCalledWith(
      deleted.task.id,
      null,
    );
    expect((await rows(deleted.task.id, deleted.runId)).tasks).toEqual([]);
  });

  it("deletes other tasks when one schedule deletion fails", async () => {
    const failing = await seedTrainingTask(db.database);
    const other = await seedTrainingTask(db.database);
    await archive(failing.workspaceId);
    await archive(other.workspaceId);
    engine.updateSchedule.mockImplementation(async (taskId: string) => {
      if (taskId === failing.task.id) throw new Error("Temporal outage");
    });

    try {
      await expect(deleteArchivedTasks(db.database, engine)).rejects.toThrow(
        "Temporal outage",
      );
    } finally {
      engine.updateSchedule.mockImplementation(async () => {});
    }

    const remaining = async (taskId: string) =>
      db.database.select().from(tasks).where(eq(tasks.id, taskId));
    expect(await remaining(failing.task.id)).toHaveLength(1);
    expect(await remaining(other.task.id)).toEqual([]);
  });

  it("keeps a task whose run is created while its schedule is deleted", async () => {
    const seed = await seedTrainingTask(db.database);
    await archive(seed.workspaceId);
    const runId = randomUUID();
    engine.updateSchedule.mockImplementation(async (taskId: string) => {
      if (taskId !== seed.task.id) return;
      await db.database.insert(trainingRuns).values({
        id: runId,
        taskId,
        stage: "queued",
        trigger: "automation",
        baseModelId: seed.input.baseModelId,
        inputCutoff: new Date(seed.input.inputCutoff),
      });
    });

    try {
      await deleteArchivedTasks(db.database, engine);
    } finally {
      engine.updateSchedule.mockImplementation(async () => {});
    }

    expect(engine.updateSchedule).toHaveBeenCalledWith(seed.task.id, null);
    const kept = await rows(seed.task.id, runId);
    expect(kept.tasks).toHaveLength(1);
    expect(kept.runs).toHaveLength(1);
  });

  it("waits for an unfinished run until it finishes or is abandoned", async () => {
    const running = await seedRun(false);
    const abandoned = await seedRun(false);
    await archive(running.workspaceId);
    await archive(abandoned.workspaceId);
    const cleanup = createTrainingArtifactCleanup(db.database, store, now);

    clock += 24 * HOUR;
    await drain(cleanup);
    expect(objects.size).toBe(8);

    await db.database
      .update(trainingRuns)
      .set({ stage: "cancelled", finishedAt: now() })
      .where(eq(trainingRuns.id, running.runId));
    clock += 3 * HOUR + 1;
    await drain(cleanup);
    expect(runObjects(running.runId)).toEqual([]);
    expect((await rows(running.task.id, running.runId)).tasks).toEqual([]);
    expect(runObjects(abandoned.runId)).toHaveLength(4);

    clock += 21 * HOUR;
    await drain(cleanup);
    expect(objects.size).toBe(0);
    expect((await rows(abandoned.task.id, abandoned.runId)).tasks).toEqual([]);
  });
});
