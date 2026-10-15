import { eq } from "drizzle-orm";
import { afterAll, beforeAll, describe, expect, it, vi } from "vitest";
import { tasks } from "../src/db/schema/index.js";
import { createTrainingService } from "../src/training/service.js";
import { createMemoryContentStore } from "./support/content-store.js";
import { createTestDatabase, type TestDatabase } from "./support/postgres.js";
import { seedTrainingTask } from "./support/training.js";
import { seedMember } from "./support/fixtures.js";

describe("task-owned schedule updates", () => {
  let db: TestDatabase;
  beforeAll(async () => {
    db = await createTestDatabase();
  });
  afterAll(() => db.dispose());

  const fixture = async () => {
    const own = await seedTrainingTask(db.database);
    const engine = {
      start: vi.fn(),
      cancel: vi.fn(),
      status: async () => "running" as const,
      updateSchedule: vi.fn().mockResolvedValue(undefined),
    };
    const service = createTrainingService(
      db.database,
      createMemoryContentStore(new Map()),
      undefined,
      engine,
    );
    return { ...own, service, engine };
  };

  it("writes a new cron and then updates Temporal directly", async () => {
    const own = await fixture();
    await own.service.updateTask(own.userId, own.workspaceId, own.task.name, {
      training_schedule: "30 0 1 * *",
    });
    expect(own.engine.updateSchedule).toHaveBeenCalledExactlyOnceWith(
      own.task.id,
      "30 0 1 * *",
    );
    const [stored] = await db.database
      .select()
      .from(tasks)
      .where(eq(tasks.id, own.task.id));
    expect(stored?.trainingSchedule).toBe("30 0 1 * *");
  });

  it("creates the default schedule when configuring task models without supplying a cron", async () => {
    const own = await fixture();
    await own.service.updateTask(own.userId, own.workspaceId, own.task.name, {
      base_model_id: own.input.baseModelId,
      comparison_model_id: own.input.comparisonModelId,
    });
    expect(own.engine.updateSchedule).toHaveBeenCalledExactlyOnceWith(
      own.task.id,
      own.task.trainingSchedule,
    );
  });

  it("disables the Temporal schedule when the cron is cleared", async () => {
    const own = await fixture();
    await own.service.updateTask(own.userId, own.workspaceId, own.task.name, {
      training_schedule: null,
    });
    expect(own.engine.updateSchedule).toHaveBeenCalledExactlyOnceWith(
      own.task.id,
      null,
    );
  });

  it("surfaces a Temporal outage and retries when the user resubmits the saved cron", async () => {
    const own = await fixture();
    own.engine.updateSchedule.mockRejectedValueOnce(
      new Error("Temporal unavailable"),
    );
    const input = { training_schedule: "0 4 * * 1" };

    await expect(
      own.service.updateTask(own.userId, own.workspaceId, own.task.name, input),
    ).rejects.toMatchObject({
      code: "unavailable",
      message: expect.stringContaining("Retry saving"),
    });
    expect(
      (await own.service.getTask(own.userId, own.workspaceId, own.task.name))
        .trainingSchedule,
    ).toBe(input.training_schedule);
    await expect(
      own.service.updateTask(own.userId, own.workspaceId, own.task.name, input),
    ).resolves.toMatchObject({ trainingSchedule: input.training_schedule });
    expect(own.engine.updateSchedule).toHaveBeenCalledTimes(2);
  });

  it("does not confirm a schedule update without a training engine", async () => {
    const own = await fixture();
    const service = createTrainingService(
      db.database,
      createMemoryContentStore(new Map()),
    );

    await expect(
      service.updateTask(own.userId, own.workspaceId, own.task.name, {
        training_schedule: null,
      }),
    ).rejects.toMatchObject({ code: "unavailable" });
  });

  it("does not touch Temporal when the task update fails validation", async () => {
    const own = await fixture();
    await expect(
      own.service.updateTask(own.userId, own.workspaceId, own.task.name, {
        training_schedule: "invalid",
      }),
    ).rejects.toMatchObject({ name: "ZodError" });
    expect(own.engine.updateSchedule).not.toHaveBeenCalled();
    expect(
      (await own.service.getTask(own.userId, own.workspaceId, own.task.name))
        .trainingSchedule,
    ).toBe(own.task.trainingSchedule);
  });

  it("does not touch Temporal for unauthorized task changes", async () => {
    const own = await fixture();
    const outsider = await seedMember(db.database, { role: "admin" });
    await expect(
      own.service.updateTask(outsider.userId, own.workspaceId, own.task.name, {
        training_schedule: null,
      }),
    ).rejects.toMatchObject({ code: "not_found" });
    expect(own.engine.updateSchedule).not.toHaveBeenCalled();
  });
});
