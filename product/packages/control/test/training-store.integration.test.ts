import { randomUUID } from "node:crypto";
import { eq } from "drizzle-orm";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import {
  tasks,
  workspaces,
  trainingRuns,
  trainingRunEvents,
} from "../src/db/schema/index.js";
import { createTrainingStore } from "../src/training/store.js";
import { createTrainingRunStore } from "../src/training/run-store.js";
import { createTestDatabase, type TestDatabase } from "./support/postgres.js";
import { seedTrainingTask, trainingAdapter } from "./support/training.js";

describe("training record store", () => {
  let db: TestDatabase;
  beforeAll(async () => {
    db = await createTestDatabase();
  });
  afterAll(() => db.dispose());

  const seedRun = async (
    taskId: string,
    overrides: Partial<typeof trainingRuns.$inferInsert> = {},
  ) => {
    const [task] = await db.database
      .select()
      .from(tasks)
      .where(eq(tasks.id, taskId));
    const [run] = await db.database
      .insert(trainingRuns)
      .values({
        id: randomUUID(),
        taskId,
        baseModelId: task!.baseModelId!,
        trigger: "manual",
        stage: "succeeded",
        inputCutoff: new Date("2026-09-20T00:00:00Z"),
        finishedAt: new Date(),
        ...overrides,
      })
      .returning();
    return run!;
  };

  it("persists the task judge independently of later workspace default changes", async () => {
    const own = await seedTrainingTask(db.database);
    const store = createTrainingStore(db.database);
    await store.updateTask(own.task.id, {
      judge_model_id: "Qwen/Qwen3-0.6B",
    });
    await db.database
      .update(workspaces)
      .set({ defaultJudgeModel: "openai/gpt-6-sol" })
      .where(eq(workspaces.id, own.workspaceId));
    expect(await store.getTask(own.workspaceId, own.task.name)).toMatchObject({
      judgeModelId: "Qwen/Qwen3-0.6B",
    });
    expect(await store.admissionContext(own.task.id)).toMatchObject({
      task: { judgeModelId: "Qwen/Qwen3-0.6B" },
    });
  });

  it("scopes task, run and admission lookups to the workspace and task filter", async () => {
    const own = await seedTrainingTask(db.database);
    const other = await seedTrainingTask(db.database);
    const reads = createTrainingStore(db.database);
    const first = await seedRun(own.task.id);
    const foreign = await seedRun(other.task.id);

    expect(await reads.getTask(own.workspaceId, own.task.name)).toMatchObject({
      id: own.task.id,
    });
    expect(
      await reads.getTaskById(own.workspaceId, other.task.id),
    ).toBeUndefined();
    expect(await reads.getRun(own.workspaceId, foreign.id)).toBeUndefined();
    expect(
      (await reads.listRuns(own.workspaceId, {})).map((run) => run.id),
    ).toEqual([first.id]);
    expect(
      await reads.listRuns(own.workspaceId, { task_id: other.task.id }),
    ).toEqual([]);
    expect(
      await reads.admissionContext({
        workspaceId: own.workspaceId,
        name: own.task.name,
      }),
    ).toMatchObject({
      task: { id: own.task.id },
      workspace: { id: own.workspaceId },
    });
    expect(
      await reads.admissionContext({
        workspaceId: own.workspaceId,
        name: "unknown",
      }),
    ).toBeUndefined();
    expect(await reads.admissionContext(other.task.id)).toMatchObject({
      task: { id: other.task.id },
    });
  });

  it("uses run ID to break creation-time ties in latest-run task summaries", async () => {
    const own = await seedTrainingTask(db.database);
    const createdAt = new Date("2026-09-25T00:00:00Z");
    await seedRun(own.task.id, {
      id: "00000000-0000-4000-8000-000000000001",
      createdAt,
    });
    const newest = await seedRun(own.task.id, {
      id: "00000000-0000-4000-8000-000000000002",
      createdAt,
      stage: "failed",
    });
    const [empty] = await db.database
      .insert(tasks)
      .values({ id: randomUUID(), workspaceId: own.workspaceId, name: "empty" })
      .returning();

    const listed = await createTrainingStore(db.database).listTasks(
      own.workspaceId,
    );

    expect(listed.map((task) => task.name)).toEqual(["empty", "triage"]);
    expect(listed.find((task) => task.id === empty!.id)?.latestRun).toBeNull();
    expect(
      listed.find((task) => task.id === own.task.id)?.latestRun,
    ).toMatchObject({ id: newest.id, stage: "failed", versionId: null });
  });

  it("finds only unfinished runs and takes the greatest successful input cutoff", async () => {
    const own = await seedTrainingTask(db.database);
    const other = await seedTrainingTask(db.database);
    const reads = createTrainingStore(db.database);
    expect(await reads.lastSuccessfulCutoff(own.task.id)).toBeNull();
    await seedRun(own.task.id, {
      inputCutoff: new Date("2026-09-22T00:00:00Z"),
      createdAt: new Date("2026-09-23T00:00:00Z"),
    });
    await seedRun(own.task.id, {
      inputCutoff: new Date("2026-09-24T00:00:00Z"),
      createdAt: new Date("2026-09-21T00:00:00Z"),
    });
    await seedRun(own.task.id, {
      stage: "failed",
      inputCutoff: new Date("2026-09-29T00:00:00Z"),
    });
    await seedRun(other.task.id, {
      inputCutoff: new Date("2026-09-30T00:00:00Z"),
    });

    expect(await reads.lastSuccessfulCutoff(own.task.id)).toEqual(
      new Date("2026-09-24T00:00:00Z"),
    );
    expect(await reads.activeRun(own.task.id)).toBeUndefined();
    const active = await seedRun(own.task.id, {
      stage: "training",
      finishedAt: null,
    });
    expect(await reads.activeRun(own.task.id)).toMatchObject({ id: active.id });
    expect(await reads.activeRun(other.task.id)).toBeUndefined();
  });

  it("pages events with an exclusive cursor without including another run's events", async () => {
    const own = await seedTrainingTask(db.database);
    const run = await seedRun(own.task.id);
    const other = await seedRun(own.task.id);
    for (const [runId, stage] of [
      [run.id, "queued"],
      [other.id, "failed"],
      [run.id, "training"],
      [run.id, "succeeded"],
    ] as const)
      await db.database.insert(trainingRunEvents).values({
        runId,
        at: new Date(),
        source: "trainer",
        attempt: 1,
        payload: { type: "stage_entered", stage },
      });
    const reads = createTrainingStore(db.database);
    const first = await reads.listRunEvents(run.id, { limit: 2 });
    const last = await reads.listRunEvents(run.id, {
      after: first[1]!.id,
      limit: 2,
    });

    expect([...first, ...last].map((event) => event.payload)).toEqual([
      { type: "stage_entered", stage: "queued" },
      { type: "stage_entered", stage: "training" },
      { type: "stage_entered", stage: "succeeded" },
    ]);
    expect(await reads.listRunEvents(run.id, { after: last[0]!.id })).toEqual(
      [],
    );
  });

  it("preserves omitted settings and allows explicit schedule disabling", async () => {
    const own = await seedTrainingTask(db.database);
    const reads = createTrainingStore(db.database);
    await reads.updateTask(own.task.id, {
      comparison_model_id: "openai/gpt-5",
    });
    expect(await reads.getTaskById(own.workspaceId, own.task.id)).toMatchObject(
      { baseModelId: own.input.baseModelId, trainingSchedule: "0 3 * * 1" },
    );
    await reads.updateTask(own.task.id, { training_schedule: null });
    expect(await reads.getTaskById(own.workspaceId, own.task.id)).toMatchObject(
      { trainingSchedule: null, baseModelId: own.input.baseModelId },
    );
    await expect(
      reads.updateTask(own.task.id, { training_schedule: "invalid" }),
    ).rejects.toMatchObject({ name: "ZodError" });
    expect(
      (await reads.getTaskById(own.workspaceId, own.task.id))?.trainingSchedule,
    ).toBeNull();
  });

  it("joins published versions into run views and scopes version reads by task", async () => {
    const own = await seedTrainingTask(db.database);
    const other = await seedTrainingTask(db.database);
    const writes = createTrainingRunStore(db.database);
    const reads = createTrainingStore(db.database);
    const id = randomUUID();
    await writes.create(id, own.input);
    await writes.transition(id, "publishing");
    const versionId = await writes.publish(
      id,
      own.input,
      trainingAdapter,
      "available",
    );

    expect(await reads.getRun(own.workspaceId, id)).toMatchObject({
      versionId,
    });
    expect(
      (await reads.listTasks(own.workspaceId))[0]?.latestRun,
    ).toMatchObject({ id, versionId, versionName: "2026-09-30" });
    expect(await reads.getVersion(other.task.id, versionId)).toBeUndefined();
    expect(
      (await reads.listVersions(own.task.id)).map((version) => version.id),
    ).toEqual([versionId]);
    expect(
      await reads.setProductionVersion(own.task.id, versionId),
    ).toMatchObject({ productionVersionId: versionId });
  });
});
