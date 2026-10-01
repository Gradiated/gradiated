import { randomUUID } from "node:crypto";
import { v7 as uuidv7 } from "uuid";
import { eq } from "drizzle-orm";
import { beforeAll, afterAll, describe, expect, it } from "vitest";
import { createTestDatabase, type TestDatabase } from "./support/postgres.js";
import { seedMember, modelInput } from "./support/fixtures.js";
import { createMemoryContentStore } from "./support/content-store.js";
import { createCatalogService } from "../src/catalog/service.js";
import {
  tasks,
  trainingRuns,
  trainingRunEvents,
  workspaces,
} from "../src/db/schema/index.js";
import { prepareTraining } from "../src/training/admission.js";
import { createTrainingRunStore } from "../src/training/run-store.js";
import { countTrainingTraces } from "../src/training/traces.js";
import { createTrainingService } from "../src/training/service.js";
import { createTrainingStore } from "../src/training/store.js";
import type {
  RunDatasetSummary,
  TrainingRunEventPayload,
  RunStage,
} from "@gradiated/contracts";
import type { TrainingInput } from "../src/training/types.js";

describe("training execution", () => {
  let db: TestDatabase;
  let baseModelId: string;
  beforeAll(async () => {
    db = await createTestDatabase();
    const model = modelInput();
    await createCatalogService(db.database).upsertModel(model);
    baseModelId = model.id;
  });
  afterAll(() => db.dispose());

  const fixture = async (count: number, capture = true) => {
    const member = await seedMember(db.database, { role: "owner" });
    await db.database
      .update(workspaces)
      .set({ traceCaptureEnabled: capture })
      .where(eq(workspaces.id, member.workspaceId));
    const taskId = randomUUID();
    await db.database.insert(tasks).values({
      id: taskId,
      workspaceId: member.workspaceId,
      name: "task",
      baseModelId,
      comparisonModelId: "openai/gpt-5",
    });
    const now = Date.now() - 10_000;
    const at = new Date(now).toISOString();
    const key = `v1/ws=${member.workspaceId}/task=task/dt=${at.slice(0, 10)}/hr=${at.slice(11, 13)}/batch.manifest.json`;
    const rows = Array.from({ length: count }, () => ({
      workspace_id: member.workspaceId,
      generation_id: uuidv7({ msecs: now }),
      task: "task",
      trace_id: null,
      model: baseModelId,
      source: "hosted",
      trainable: true,
      started_at: at,
      completed_at: at,
      usage: null,
      retention_days: 30,
      offset: 0,
      length: 1,
    }));
    const objects = new Map([
      [
        key,
        Buffer.from(
          JSON.stringify({
            schema: "gradiated.generation-content-manifest/1",
            generations: [...rows, ...rows],
          }),
        ),
      ],
    ]);
    const store = createMemoryContentStore(objects);
    const input: TrainingInput = {
      taskId,
      workspaceId: member.workspaceId,
      name: "task",
      baseModelId,
      comparisonModelId: "openai/gpt-5",
      judgeModelId: "openai/gpt-5",
      inputCutoff: new Date().toISOString(),
      trigger: "manual",
      requestedBy: member.userId,
    };

    return { ...member, taskId, store, input, at, objects };
  };

  it.each([
    ["manual", 99, false],
    ["manual", 100, true],
    ["automation", 499, false],
    ["automation", 500, true],
  ] as const)(
    "admits %s with %i distinct traces: %s",
    async (trigger, count, allowed) => {
      const f = await fixture(count);
      const promise = prepareTraining(
        db.database,
        f.store,
        f.taskId,
        trigger,
        f.userId,
      );
      if (allowed)
        await expect(promise).resolves.toMatchObject({
          taskId: f.taskId,
          trigger,
        });
      else
        await expect(promise).rejects.toMatchObject({
          code: "insufficient_traces",
        });
    },
  );

  it.each(["manual", "automation"] as const)(
    "reconciles a closed execution before %s admission",
    async (trigger) => {
      const f = await fixture(500);
      const writes = createTrainingRunStore(db.database);
      const reads = createTrainingStore(db.database);
      const oldId = randomUUID();
      await writes.create(oldId, f.input, "generated-schedule-id");
      const engine = {
        start: async () => randomUUID(),
        cancel: async () => {},
        updateSchedule: async () => {},
        status: async (workflowId: string, runId: string) => {
          expect([workflowId, runId]).toEqual(["generated-schedule-id", oldId]);
          return "failed" as const;
        },
      };
      await expect(
        prepareTraining(db.database, f.store, f.taskId, trigger, null, engine),
      ).resolves.toMatchObject({ taskId: f.taskId, trigger });
      expect(await reads.activeRun(f.taskId)).toBeUndefined();
      expect(await reads.getRun(f.workspaceId, oldId)).toMatchObject({
        stage: "failed",
        finishedAt: expect.any(Date),
      });
      expect(await writes.create(randomUUID(), f.input)).toBe(true);
    },
  );

  it.each(["failed", "cancelled", "succeeded"] as const)(
    "uses only successful cutoffs after %s",
    async (stage) => {
      const f = await fixture(100);
      await db.database.insert(trainingRuns).values({
        id: randomUUID(),
        taskId: f.taskId,
        trigger: "automation",
        stage,
        baseModelId,
        inputCutoff: new Date(),
        finishedAt: new Date(),
      });
      const promise = prepareTraining(
        db.database,
        f.store,
        f.taskId,
        "manual",
        f.userId,
      );
      if (stage === "succeeded")
        await expect(promise).rejects.toMatchObject({
          code: "insufficient_traces",
        });
      else await expect(promise).resolves.toMatchObject({ taskId: f.taskId });
    },
  );

  it("stops manifest reads at the threshold and deduplicates repeated trace IDs", async () => {
    const f = await fixture(100);
    f.objects.set(
      `v1/ws=${f.workspaceId}/task=task/dt=2026-01-01/hr=00/old.manifest.json`,
      Buffer.from("invalid"),
    );
    expect(
      await countTrainingTraces(f.store, {
        workspaceId: f.workspaceId,
        task: "task",
        since: null,
        cutoff: new Date(),
        threshold: 100,
      }),
    ).toBe(100);
    expect(f.store.read).toHaveBeenCalledTimes(1);
  });

  it.each(["relay", "import"])(
    "does not admit untrainable %s captures",
    async (source) => {
      const f = await fixture(500);
      for (const [key, bytes] of f.objects) {
        const manifest = JSON.parse(bytes.toString());
        for (const row of manifest.generations) {
          row.source = source;
          row.trainable = false;
        }
        f.objects.set(key, Buffer.from(JSON.stringify(manifest)));
      }
      await expect(
        prepareTraining(db.database, f.store, f.taskId, "manual", f.userId),
      ).rejects.toMatchObject({ code: "insufficient_traces" });
    },
  );

  it("counts only trainable traces in mixed batches", async () => {
    const f = await fixture(101);
    for (const [key, bytes] of f.objects) {
      const manifest = JSON.parse(bytes.toString());
      const excluded = manifest.generations[0].generation_id;
      for (const row of manifest.generations) {
        if (row.generation_id === excluded) row.trainable = false;
      }
      f.objects.set(key, Buffer.from(JSON.stringify(manifest)));
    }
    expect(
      await countTrainingTraces(f.store, {
        workspaceId: f.workspaceId,
        task: "task",
        since: null,
        cutoff: new Date(),
        threshold: 500,
      }),
    ).toBe(100);
  });

  it("counts late arrivals from older request-hour prefixes", async () => {
    const f = await fixture(100);
    const oldAt = new Date(Date.now() - 86_400_000).toISOString();
    const body = JSON.parse([...f.objects.values()][0]!.toString());
    for (const row of body.generations) row.started_at = oldAt;
    f.objects.clear();
    f.objects.set(
      `v1/ws=${f.workspaceId}/task=task/dt=${oldAt.slice(0, 10)}/hr=${oldAt.slice(11, 13)}/late.manifest.json`,
      Buffer.from(JSON.stringify(body)),
    );
    expect(
      await countTrainingTraces(f.store, {
        workspaceId: f.workspaceId,
        task: "task",
        since: new Date(Date.now() - 3_600_000),
        cutoff: new Date(),
        threshold: 100,
      }),
    ).toBe(100);
  });

  it("requires capture for automatic runs but allows manual runs on retained traces", async () => {
    const f = await fixture(500, false);
    await expect(
      prepareTraining(db.database, f.store, f.taskId, "automation", null),
    ).rejects.toMatchObject({ code: "training_not_configured" });
    await expect(
      prepareTraining(db.database, f.store, f.taskId, "manual", f.userId),
    ).resolves.toMatchObject({ taskId: f.taskId });
  });

  it("atomically records stages once and never reopens a cancelled run", async () => {
    const f = await fixture(100);
    const store = createTrainingRunStore(db.database);
    const id = randomUUID();
    await store.create(id, f.input);
    await store.create(id, f.input);
    await Promise.all([
      store.transition(id, "training"),
      store.transition(id, "training"),
    ]);
    await store.transition(id, "cancelling");
    await store.transition(id, "evaluating");
    await store.transition(id, "cancelled");
    await store.transition(id, "succeeded");
    const [run] = await db.database
      .select()
      .from(trainingRuns)
      .where(eq(trainingRuns.id, id));
    const events = await db.database
      .select()
      .from(trainingRunEvents)
      .where(eq(trainingRunEvents.runId, id));
    expect(run?.stage).toBe("cancelled");
    expect(run?.finishedAt).not.toBeNull();
    expect(
      events
        .filter(({ payload }) => payload.type === "stage_entered")
        .map(
          ({ payload }) => payload.type === "stage_entered" && payload.stage,
        ),
    ).toEqual(["queued", "training", "cancelling", "cancelled"]);
  });

  it("rejects malformed writes and preserves the run when event validation fails", async () => {
    const f = await fixture(100);
    const store = createTrainingRunStore(db.database);
    const id = randomUUID();
    await expect(
      store.create(id, { ...f.input, requestedBy: "not-a-uuid" }),
    ).rejects.toMatchObject({ name: "ZodError" });
    expect(
      await db.database
        .select()
        .from(trainingRuns)
        .where(eq(trainingRuns.id, id)),
    ).toEqual([]);
    await store.create(id, f.input);

    const dataset: RunDatasetSummary = {
      eligible_examples: 100,
      duplicates_removed: 0,
      train: 80,
      validation: 10,
      test: 10,
    };
    await expect(
      store.result(
        id,
        "dataset",
        { ...dataset, train: -1 },
        { type: "dataset_built", ...dataset },
        1,
      ),
    ).rejects.toMatchObject({ name: "ZodError" });
    await expect(
      store.result(
        id,
        "dataset",
        dataset,
        { type: "stage_entered", stage: "invalid" as RunStage },
        1,
      ),
    ).rejects.toMatchObject({ name: "ZodError" });
    const [run] = await db.database
      .select()
      .from(trainingRuns)
      .where(eq(trainingRuns.id, id));
    expect(run?.dataset).toBeNull();
    expect(
      await db.database
        .select()
        .from(trainingRunEvents)
        .where(eq(trainingRunEvents.runId, id)),
    ).toHaveLength(2);
  });

  it("persists parsed JSON and parses database JSON again on reads", async () => {
    const f = await fixture(100);
    const writes = createTrainingRunStore(db.database);
    const reads = createTrainingStore(db.database);
    const id = randomUUID();
    await writes.create(id, f.input);
    const dataset = {
      eligible_examples: 100,
      duplicates_removed: 0,
      train: 80,
      validation: 10,
      test: 10,
      unexpected: "discard",
    };
    await writes.result(
      id,
      "dataset",
      dataset,
      { type: "dataset_built", ...dataset },
      1,
    );
    const [stored] = await db.database
      .select()
      .from(trainingRuns)
      .where(eq(trainingRuns.id, id));
    expect(stored?.dataset).not.toHaveProperty("unexpected");
    const events = await reads.listRunEvents(id, {});
    expect(events).toHaveLength(3);
    expect(events[2]?.payload).not.toHaveProperty("unexpected");

    await db.database
      .update(trainingRuns)
      .set({ dataset })
      .where(eq(trainingRuns.id, id));
    expect((await reads.getRun(f.workspaceId, id))?.dataset).not.toHaveProperty(
      "unexpected",
    );
    await db.database
      .update(trainingRuns)
      .set({ dataset: { ...dataset, train: -1 } })
      .where(eq(trainingRuns.id, id));
    await expect(reads.getRun(f.workspaceId, id)).rejects.toMatchObject({
      name: "ZodError",
    });
  });

  it("rejects corrupt persisted events before returning them", async () => {
    const f = await fixture(100);
    const id = randomUUID();
    await createTrainingRunStore(db.database).create(id, f.input);
    await db.database.insert(trainingRunEvents).values({
      runId: id,
      at: new Date(),
      source: "trainer",
      attempt: 1,
      payload: {
        type: "stage_entered",
        stage: "invalid",
      } as unknown as TrainingRunEventPayload,
    });
    await expect(
      createTrainingStore(db.database).listRunEvents(id, {}),
    ).rejects.toMatchObject({ name: "ZodError" });
  });

  it("starts by task ID only within the authorized workspace", async () => {
    const f = await fixture(100);
    const outsider = await seedMember(db.database, { role: "owner" });
    const started: TrainingInput[] = [];
    const runId = randomUUID();
    const service = createTrainingService(db.database, f.store, undefined, {
      start: async (input) => {
        started.push(input);
        return runId;
      },
      status: async () => "running" as const,
      updateSchedule: async () => {},
      cancel: async () => {},
    });
    await expect(
      service.startRun(outsider.userId, outsider.workspaceId, f.taskId),
    ).rejects.toMatchObject({ code: "not_found" });
    await expect(
      service.startRun(f.userId, f.workspaceId, randomUUID()),
    ).rejects.toMatchObject({ code: "not_found" });
    expect(started).toEqual([]);
    await expect(
      service.startRun(f.userId, f.workspaceId, f.taskId),
    ).resolves.toEqual({ id: runId });
    expect(started).toMatchObject([
      { taskId: f.taskId, workspaceId: f.workspaceId },
    ]);
  });

  it("makes an accepted run visible and cancellable before the worker starts", async () => {
    const f = await fixture(100);
    const id = randomUUID();
    const cancelled: string[] = [];
    const service = createTrainingService(db.database, f.store, undefined, {
      start: async () => id,
      status: async () => "running" as const,
      updateSchedule: async () => {},
      cancel: async (taskId, runId) => {
        expect(taskId).toBe(f.taskId);
        cancelled.push(runId);
      },
    });
    await expect(
      service.startRun(f.userId, f.workspaceId, f.taskId),
    ).resolves.toEqual({ id });
    await expect(
      service.getRun(f.userId, f.workspaceId, id),
    ).resolves.toMatchObject({
      id,
      stage: "queued",
    });
    expect(
      await service.listRuns(f.userId, f.workspaceId, { task_id: f.taskId }),
    ).toMatchObject([{ id, stage: "queued" }]);
    await service.cancelRun(f.userId, f.workspaceId, id);
    expect(cancelled).toEqual([id]);

    await createTrainingRunStore(db.database).create(id, f.input);
    const events = await db.database
      .select()
      .from(trainingRunEvents)
      .where(eq(trainingRunEvents.runId, id));
    expect(
      events.filter(({ payload }) => payload.type === "run_created"),
    ).toHaveLength(1);
    expect(
      events.filter(({ payload }) => payload.type === "cancel_requested"),
    ).toHaveLength(1);
    await expect(
      service.getRun(f.userId, f.workspaceId, id),
    ).resolves.toMatchObject({
      cancelRequestedAt: expect.any(Date),
    });
  });

  it("preserves worker progress when the worker creates the run first", async () => {
    const f = await fixture(100);
    const id = randomUUID();
    const runs = createTrainingRunStore(db.database);
    const service = createTrainingService(db.database, f.store, undefined, {
      start: async (input) => {
        await runs.create(id, input);
        await runs.transition(id, "building_dataset");
        return id;
      },
      status: async () => "running" as const,
      updateSchedule: async () => {},
      cancel: async () => {},
    });
    await service.startRun(f.userId, f.workspaceId, f.taskId);
    await expect(
      service.getRun(f.userId, f.workspaceId, id),
    ).resolves.toMatchObject({
      stage: "building_dataset",
    });
    const events = await db.database
      .select()
      .from(trainingRunEvents)
      .where(eq(trainingRunEvents.runId, id));
    expect(
      events.filter(({ payload }) => payload.type === "run_created"),
    ).toHaveLength(1);
  });

  it("persists staggered defaults and rechecks disabled automation at execution time", async () => {
    const f = await fixture(500);
    const service = createTrainingService(db.database, f.store);
    const before = await service.getTask(f.userId, f.workspaceId, "task");
    expect(before.trainingSchedule).toMatch(/^\d+ \d+ \* \* [0-6]$/);
    await service.updateTask(f.userId, f.workspaceId, "task", {
      training_schedule: "0 3 1 * *",
    });
    expect(
      (await service.getTask(f.userId, f.workspaceId, "task")).trainingSchedule,
    ).toBe("0 3 1 * *");
    await service.updateTask(f.userId, f.workspaceId, "task", {
      training_schedule: null,
    });
    await expect(
      prepareTraining(db.database, f.store, f.taskId, "automation", null),
    ).rejects.toMatchObject({ code: "training_not_configured" });
    await expect(
      prepareTraining(db.database, f.store, f.taskId, "manual", f.userId),
    ).resolves.toMatchObject({ taskId: f.taskId });
    const after = await service.getTask(f.userId, f.workspaceId, "task");
    expect(after.trainingSchedule).toBeNull();
  });

  it("rejects a second active run and confines cancellation to the owning workspace", async () => {
    const f = await fixture(100);
    const store = createTrainingRunStore(db.database);
    const id = randomUUID();
    await store.create(id, f.input);
    await expect(
      prepareTraining(db.database, f.store, f.taskId, "manual", f.userId),
    ).rejects.toMatchObject({ code: "already_training" });
    const outsider = await seedMember(db.database, { role: "owner" });
    const cancelled: string[] = [];
    const service = createTrainingService(db.database, f.store, undefined, {
      start: async () => id,
      status: async () => "running" as const,
      updateSchedule: async () => {},
      cancel: async (_taskId, runId) => {
        cancelled.push(runId);
      },
    });
    await expect(
      service.cancelRun(outsider.userId, f.workspaceId, id),
    ).rejects.toMatchObject({ code: "not_found" });
    await service.cancelRun(f.userId, f.workspaceId, id);
    expect(cancelled).toEqual([id]);
  });
});
