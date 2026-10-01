import { eq } from "drizzle-orm";
import { randomUUID } from "node:crypto";
import { createTestDatabase } from "../../../packages/control/test/support/postgres.js";
import {
  seedMember,
  modelInput,
} from "../../../packages/control/test/support/fixtures.js";
import { createMemoryContentStore } from "../../../packages/control/test/support/content-store.js";
import {
  tasks,
  workspaces,
  trainingRuns,
  organizations,
} from "../../../packages/control/src/db/schema/index.js";
import {
  createCatalogService,
  createTemporalTrainingEngine,
  createTrainingService,
  createTrainingRunStore,
  trainingScheduleId,
} from "@gradiated/control";
import { afterAll, beforeAll, expect, it, vi } from "vitest";
import { seedTrainingTask } from "../../../packages/control/test/support/training.js";
import { ScheduleOverlapPolicy } from "@temporalio/client";
import { TestWorkflowEnvironment } from "@temporalio/testing";
import { createDataConverter } from "@gradiated/temporal";
import { runTrainingWorker } from "../src/training/worker.js";

let environment: TestWorkflowEnvironment;
beforeAll(async () => {
  environment = await TestWorkflowEnvironment.createLocal({
    client: {
      dataConverter: await createDataConverter({
        currentKeyId: "test",
        keys: { test: Buffer.alloc(32, 1).toString("base64") },
      }),
    },
  });
}, 60_000);
afterAll(async () => {
  await environment?.teardown();
});

const workerEnvironment = (): NodeJS.ProcessEnv => ({
  NODE_ENV: "test",
  TEMPORAL_ADDRESS: environment.address,
  TEMPORAL_NAMESPACE: "default",
  TEMPORAL_PAYLOAD_KEY_ID: "test",
  TEMPORAL_PAYLOAD_KEYS: JSON.stringify({
    test: Buffer.alloc(32, 1).toString("base64"),
  }),
});

it.each(["before startup", "during readiness"] as const)(
  "shuts down when aborted %s",
  async (timing) => {
    const db = await createTestDatabase();
    const abort = new AbortController();
    const onReady = vi.fn(async () => abort.abort());
    if (timing === "before startup") abort.abort();

    try {
      await runTrainingWorker({
        database: db.database,
        contents: createMemoryContentStore(new Map()),
        environment: workerEnvironment(),
        signal: abort.signal,
        onReady,
      });
      expect(onReady).toHaveBeenCalledTimes(
        timing === "before startup" ? 0 : 1,
      );
    } finally {
      await db.dispose();
    }
  },
  30_000,
);

it("shuts down and preserves the error when readiness fails", async () => {
  const db = await createTestDatabase();
  const failure = new Error("Readiness failed");

  try {
    await expect(
      runTrainingWorker({
        database: db.database,
        contents: createMemoryContentStore(new Map()),
        environment: workerEnvironment(),
        signal: new AbortController().signal,
        onReady: async () => {
          throw failure;
        },
      }),
    ).rejects.toBe(failure);
  } finally {
    await db.dispose();
  }
}, 30_000);

it("creates, updates, disables and re-enables a schedule directly across replicas", async () => {
  const taskId = randomUUID();
  const engine = createTemporalTrainingEngine(environment.client);
  const handle = environment.client.schedule.getHandle(
    trainingScheduleId(taskId),
  );

  try {
    await Promise.all([
      engine.updateSchedule(taskId, "45 3 * * MON"),
      engine.updateSchedule(taskId, "45 3 * * MON"),
    ]);
    const schedule = await handle.describe();
    expect(schedule.spec.calendars?.[0]).toMatchObject({
      minute: [{ start: 45, end: 45, step: 1 }],
      hour: [{ start: 3, end: 3, step: 1 }],
      dayOfWeek: [{ start: "MONDAY", end: "MONDAY", step: 1 }],
    });
    expect(schedule.action).toMatchObject({
      workflowType: "trainingTaskV1",
      taskQueue: "training-v1",
      args: [taskId],
    });
    expect(schedule.policies).toMatchObject({
      overlap: ScheduleOverlapPolicy.SKIP,
      catchupWindow: 3600000,
    });
    await engine.updateSchedule(taskId, "30 0 1 * *");
    expect((await handle.describe()).spec.calendars?.[0]).toMatchObject({
      minute: [{ start: 30, end: 30, step: 1 }],
      dayOfMonth: [{ start: 1, end: 1, step: 1 }],
    });
    await engine.updateSchedule(taskId, null);
    await expect(handle.describe()).rejects.toThrow();
    await engine.updateSchedule(taskId, null);
    await engine.updateSchedule(taskId, "0 3 * * 1");
    expect((await handle.describe()).state.paused).toBe(false);
  } finally {
    await engine.updateSchedule(taskId, null);
  }
}, 30000);

it("writes the Temporal schedule when the task is modified", async () => {
  const db = await createTestDatabase();
  const engine = createTemporalTrainingEngine(environment.client);
  const member = await seedMember(db.database, { role: "owner" });
  const model = modelInput();
  await createCatalogService(db.database).upsertModel(model);
  const taskId = randomUUID();
  await db.database.insert(tasks).values({
    id: taskId,
    workspaceId: member.workspaceId,
    name: "task",
    baseModelId: model.id,
    comparisonModelId: "openai/gpt-5",
  });
  const service = createTrainingService(
    db.database,
    createMemoryContentStore(new Map()),
    undefined,
    engine,
  );
  const handle = environment.client.schedule.getHandle(
    trainingScheduleId(taskId),
  );

  try {
    await service.updateTask(member.userId, member.workspaceId, "task", {
      training_schedule: "30 0 1 * *",
    });
    expect((await handle.describe()).spec.calendars?.[0]).toMatchObject({
      dayOfMonth: [{ start: 1, end: 1, step: 1 }],
    });
    await db.database
      .update(workspaces)
      .set({ archivedAt: new Date() })
      .where(eq(workspaces.id, member.workspaceId));
    expect((await handle.describe()).state.paused).toBe(false);
    await db.database
      .update(workspaces)
      .set({ archivedAt: null })
      .where(eq(workspaces.id, member.workspaceId));
    await service.updateTask(member.userId, member.workspaceId, "task", {
      training_schedule: null,
    });
    await expect(handle.describe()).rejects.toThrow();
  } finally {
    await engine.updateSchedule(taskId, null);
    await db.dispose();
  }
}, 30000);

it("starts and shuts down the worker with encrypted clients and PostgreSQL run state", async () => {
  const db = await createTestDatabase();
  const abort = new AbortController();
  let running: Promise<void> | undefined;
  try {
    const member = await seedMember(db.database, { role: "owner" });
    const model = modelInput();
    await createCatalogService(db.database).upsertModel(model);
    const taskId = randomUUID();
    await db.database.insert(tasks).values({
      id: taskId,
      workspaceId: member.workspaceId,
      name: "synthetic-task",
      baseModelId: model.id,
      comparisonModelId: "openai/gpt-5",
    });
    const contents = createMemoryContentStore(new Map());
    let ready!: () => void;
    const readiness = new Promise<void>((resolve) => {
      ready = resolve;
    });
    running = runTrainingWorker({
      database: db.database,
      contents,
      signal: abort.signal,
      environment: workerEnvironment(),
      onReady: async () => ready(),
    });
    await Promise.race([readiness, running]);
    const engine = createTemporalTrainingEngine(environment.client);
    for (const condition of [
      "capture disabled",
      "archived",
      "suspended",
    ] as const) {
      await db.database
        .update(workspaces)
        .set({
          traceCaptureEnabled: condition !== "capture disabled",
          archivedAt: condition === "archived" ? new Date() : null,
        })
        .where(eq(workspaces.id, member.workspaceId));
      await db.database
        .update(organizations)
        .set({ status: condition === "suspended" ? "suspended" : "active" })
        .where(eq(organizations.id, member.organizationId));
      const scheduled = await environment.client.workflow.start(
        "trainingTaskV1",
        {
          workflowId: `eligibility-${randomUUID()}`,
          taskQueue: "training-v1",
          args: [taskId],
        },
      );
      await scheduled.result();
      expect(
        await db.database
          .select()
          .from(trainingRuns)
          .where(eq(trainingRuns.taskId, taskId)),
      ).toEqual([]);
    }
    await db.database
      .update(organizations)
      .set({ status: "active" })
      .where(eq(organizations.id, member.organizationId));
    await db.database
      .update(workspaces)
      .set({ archivedAt: null })
      .where(eq(workspaces.id, member.workspaceId));

    const id = await engine.start({
      taskId,
      workspaceId: member.workspaceId,
      name: "synthetic-task",
      baseModelId: model.id,
      comparisonModelId: "openai/gpt-5",
      judgeModelId: "openai/gpt-5",
      inputCutoff: new Date().toISOString(),
      trigger: "manual",
      requestedBy: member.userId,
    });
    await environment.client.workflow
      .getHandle(`training-${taskId}`, id)
      .result();
    const service = createTrainingService(db.database, contents);
    expect(
      await service.getRun(member.userId, member.workspaceId, id),
    ).toMatchObject({ stage: "succeeded" });
    expect(
      await service.listVersions(
        member.userId,
        member.workspaceId,
        "synthetic-task",
      ),
    ).toMatchObject({ versions: [{ status: "unavailable" }] });
  } finally {
    abort.abort();
    await running;
    await db.dispose();
  }
}, 60_000);

it("stores the SFT run workflow on a per-task cron schedule", async () => {
  const taskId = randomUUID();
  const engine = createTemporalTrainingEngine(
    environment.client,
    "trainingRunV2",
    "trainingRunV2",
  );
  await engine.updateSchedule(taskId, "15 3 * * 2");
  const handle = environment.client.schedule.getHandle(
    `training-task-${taskId}`,
  );
  const schedule = await handle.describe();
  expect(schedule.action).toMatchObject({
    type: "startWorkflow",
    workflowType: "trainingRunV2",
    args: [taskId],
  });
  await engine.updateSchedule(taskId, null);
  await expect(handle.describe()).rejects.toThrow();
});

it("cancels the exact scheduled execution using its generated workflow ID", async () => {
  const taskId = randomUUID();
  const handle = await environment.client.workflow.start("trainingRunV2", {
    workflowId: `scheduled-${taskId}-${randomUUID()}`,
    taskQueue: randomUUID(),
    args: [taskId],
  });
  try {
    const engine = createTemporalTrainingEngine(environment.client);
    await engine.cancel(taskId, handle.firstExecutionRunId, handle.workflowId);
    const history = await handle.fetchHistory();
    expect(
      history.events?.some(
        (event) => event.workflowExecutionCancelRequestedEventAttributes,
      ),
    ).toBe(true);
  } finally {
    await handle.terminate();
  }
});

it.each(["timeout", "termination"] as const)(
  "reconciles a hard workflow %s outside workflow cleanup and admits the next run",
  async (ending) => {
    const db = await createTestDatabase();
    try {
      const own = await seedTrainingTask(db.database);
      const writes = createTrainingRunStore(db.database);
      const handle = await environment.client.workflow.start("trainingRunV2", {
        workflowId: `scheduled-${randomUUID()}`,
        taskQueue: randomUUID(),
        args: [own.input],
        workflowExecutionTimeout: "1 second",
      });
      await writes.create(
        handle.firstExecutionRunId,
        own.input,
        handle.workflowId,
      );
      if (ending === "termination") await handle.terminate();
      await expect(handle.result()).rejects.toThrow();

      const service = createTrainingService(
        db.database,
        createMemoryContentStore(new Map()),
        undefined,
        createTemporalTrainingEngine(environment.client),
      );
      const [tasks, runs] = await Promise.all([
        service.listTasks(own.userId, own.workspaceId),
        service.listRuns(own.userId, own.workspaceId),
      ]);
      expect(tasks[0]?.latestRun).toMatchObject({
        stage: "failed",
        finishedAt: expect.any(Date),
      });
      expect(runs[0]).toMatchObject({
        stage: "failed",
        finishedAt: expect.any(Date),
      });
      const events = await service.listRunEvents(
        own.userId,
        own.workspaceId,
        handle.firstExecutionRunId,
        { limit: 100 },
      );
      expect(
        events.filter(({ payload }) => payload.type === "run_finished"),
      ).toHaveLength(1);
      expect(await writes.create(randomUUID(), own.input)).toBe(true);
    } finally {
      await db.dispose();
    }
  },
  30_000,
);
