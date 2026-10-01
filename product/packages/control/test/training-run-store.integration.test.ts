import { randomUUID } from "node:crypto";
import type { RunDatasetSummary, RunEvaluation } from "@gradiated/contracts";
import { eq } from "drizzle-orm";
import { afterAll, beforeAll, describe, expect, it, vi } from "vitest";
import {
  trainingRuns,
  trainingRunEvents,
  taskVersions,
} from "../src/db/schema/index.js";
import { createQwenSftModelConfiguration } from "../src/catalog/models/qwen3-0-6b.js";
import { createCatalogService } from "../src/catalog/service.js";
import { createTrainingService } from "../src/training/service.js";
import { createMemoryContentStore } from "./support/content-store.js";
import { createTrainingRunStore } from "../src/training/run-store.js";
import { createTrainingStore } from "../src/training/store.js";
import { createTestDatabase, type TestDatabase } from "./support/postgres.js";
import { seedTrainingTask, trainingAdapter } from "./support/training.js";

const dataset: RunDatasetSummary = {
  eligible_examples: 100,
  duplicates_removed: 0,
  train: 80,
  validation: 10,
  test: 10,
};

describe("transactional training run store", () => {
  let db: TestDatabase;
  beforeAll(async () => {
    db = await createTestDatabase();
  });
  afterAll(() => db.dispose());

  it("allows a persisted training-only base while keeping it unavailable for inference", async () => {
    const own = await seedTrainingTask(db.database);
    const qwen = createQwenSftModelConfiguration();
    const model = await createCatalogService(db.database).upsertModel(qwen);
    expect(model.status).toBe("unavailable");
    const service = createTrainingService(
      db.database,
      createMemoryContentStore(new Map()),
    );
    await expect(
      service.updateTask(own.userId, own.workspaceId, own.task.name, {
        base_model_id: qwen.id,
      }),
    ).resolves.toMatchObject({ baseModelId: qwen.id });
  });

  it("validates and deduplicates trainer observations while rejecting lifecycle events", async () => {
    const own = await seedTrainingTask(db.database);
    const writes = createTrainingRunStore(db.database);
    const reads = createTrainingStore(db.database);
    const id = randomUUID();
    await writes.create(id, own.input);
    const observation = {
      type: "trainer_observation" as const,
      name: "validation",
      message: "Validation complete",
      metrics: { validation_loss: 0.5 },
      details: { method: "sft" },
    };
    await Promise.all([
      writes.appendTrainerEvents(id, 1, [observation]),
      writes.appendTrainerEvents(id, 1, [observation]),
    ]);
    const events = await reads.listRunEvents(id, {});
    expect(events.filter((event) => event.source === "trainer")).toMatchObject([
      { attempt: 1, payload: observation },
    ]);
    await expect(
      writes.appendTrainerEvents(id, 1, [
        { type: "stage_entered", stage: "succeeded" },
      ]),
    ).rejects.toThrow("lifecycle");
    await expect(
      writes.appendTrainerEvents(id, 0, [observation]),
    ).rejects.toMatchObject({ name: "ZodError" });
    await writes.transition(id, "cancelled");
    await writes.appendTrainerEvents(id, 2, [observation]);
    expect(
      (await reads.listRunEvents(id, {})).filter(
        (event) => event.source === "trainer",
      ),
    ).toHaveLength(1);
  });

  it("creates one run and one initial event pair under concurrent workflow retries", async () => {
    const own = await seedTrainingTask(db.database);
    const writes = createTrainingRunStore(db.database);
    const reads = createTrainingStore(db.database);
    const id = randomUUID();

    await Promise.all(
      Array.from({ length: 4 }, () => writes.create(id, own.input)),
    );

    expect(
      (await reads.listRuns(own.workspaceId, {})).map((run) => run.id),
    ).toEqual([id]);
    expect(
      (await reads.listRunEvents(id, {})).map((event) => event.payload),
    ).toEqual([
      {
        type: "run_created",
        trigger: "manual",
        requested_by: own.userId,
        base_model_id: own.input.baseModelId,
      },
      { type: "stage_entered", stage: "queued" },
    ]);
  });

  it("admits only one concurrent manual or scheduled run and retains its workflow identity", async () => {
    const own = await seedTrainingTask(db.database);
    const writes = createTrainingRunStore(db.database);
    const ids = [randomUUID(), randomUUID()];
    const workflowIds = [
      `training-${own.input.taskId}`,
      "scheduled-training-2026-10-01",
    ];
    const inputs = [
      own.input,
      { ...own.input, trigger: "automation" as const, requestedBy: null },
    ];
    const admitted = await Promise.all(
      ids.map((id, index) =>
        writes.create(id, inputs[index]!, workflowIds[index]),
      ),
    );
    expect(admitted.filter(Boolean)).toHaveLength(1);
    const winner = admitted.indexOf(true);
    const reads = createTrainingStore(db.database);
    const run = await reads.getRun(own.workspaceId, ids[winner]!);
    expect(run?.workflowId).toBe(workflowIds[winner]);
    expect(await writes.create(ids[winner]!, inputs[winner]!)).toBe(true);
    expect(
      (await reads.getRun(own.workspaceId, ids[winner]!))?.workflowId,
    ).toBe(workflowIds[winner]);
    expect(await reads.listRunEvents(ids[1 - winner]!, {})).toEqual([]);
  });

  it("cancels a scheduled run using its stored execution identity", async () => {
    const own = await seedTrainingTask(db.database);
    const id = randomUUID();
    const workflowId = "scheduled-training-2026-10-01";
    await createTrainingRunStore(db.database).create(id, own.input, workflowId);
    let cancelled: unknown;
    const service = createTrainingService(
      db.database,
      createMemoryContentStore(new Map()),
      undefined,
      {
        start: async () => id,
        status: async () => "running" as const,
        updateSchedule: async () => {},
        cancel: async (...args) => {
          cancelled = args;
        },
      },
    );
    await service.cancelRun(own.userId, own.workspaceId, id);
    expect(cancelled).toEqual([own.input.taskId, id, workflowId]);
  });

  it("preserves an active run and readable pages when Temporal status is unavailable", async () => {
    const own = await seedTrainingTask(db.database);
    const writes = createTrainingRunStore(db.database);
    const reads = createTrainingStore(db.database);
    const id = randomUUID();
    await writes.create(id, own.input);
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const service = createTrainingService(
      db.database,
      createMemoryContentStore(new Map()),
      undefined,
      {
        start: async () => id,
        cancel: async () => {},
        updateSchedule: async () => {},
        status: async () => {
          throw new Error("Temporal unavailable");
        },
      },
    );
    try {
      expect(
        await service.getRun(own.userId, own.workspaceId, id),
      ).toMatchObject({ stage: "queued", finishedAt: null });
      expect(await reads.activeRun(own.input.taskId)).toMatchObject({ id });
      expect(await writes.create(randomUUID(), own.input)).toBe(false);
    } finally {
      warn.mockRestore();
    }
  });

  it("records cancellation once under concurrent retries without changing the current stage", async () => {
    const own = await seedTrainingTask(db.database);
    const writes = createTrainingRunStore(db.database);
    const reads = createTrainingStore(db.database);
    const id = randomUUID();
    await writes.create(id, own.input);
    await writes.transition(id, "training");

    await Promise.all(
      Array.from({ length: 4 }, () =>
        writes.requestCancellation(id, own.userId),
      ),
    );

    expect(await reads.getRun(own.workspaceId, id)).toMatchObject({
      stage: "training",
      cancelRequestedAt: expect.any(Date),
      finishedAt: null,
    });
    expect(
      (await reads.listRunEvents(id, {})).filter(
        (event) => event.payload.type === "cancel_requested",
      ),
    ).toHaveLength(1);
  });

  it("commits one result and its matching event under concurrent activity retries", async () => {
    const own = await seedTrainingTask(db.database);
    const writes = createTrainingRunStore(db.database);
    const reads = createTrainingStore(db.database);
    const id = randomUUID();
    await writes.create(id, own.input);
    const alternative = { ...dataset, train: 75 };

    await Promise.all(
      [dataset, alternative].map((value, index) =>
        writes.result(
          id,
          "dataset",
          value,
          { type: "dataset_built", ...value },
          index + 1,
        ),
      ),
    );

    const run = await reads.getRun(own.workspaceId, id);
    const events = (await reads.listRunEvents(id, {})).filter(
      (event) => event.payload.type === "dataset_built",
    );
    expect(events).toHaveLength(1);
    expect(events[0]?.payload).toEqual({
      type: "dataset_built",
      ...run!.dataset,
    });
    expect([dataset, alternative]).toContainEqual(run!.dataset);
  });

  it.each(["cancelling", "cancelled", "failed", "succeeded"] as const)(
    "ignores late activity results after %s",
    async (stage) => {
      const own = await seedTrainingTask(db.database);
      const writes = createTrainingRunStore(db.database);
      const reads = createTrainingStore(db.database);
      const id = randomUUID();
      await writes.create(id, own.input);
      await writes.transition(id, stage);
      const before = await reads.listRunEvents(id, {});

      await writes.result(
        id,
        "dataset",
        dataset,
        { type: "dataset_built", ...dataset },
        1,
      );
      await writes.transition(id, "training");

      expect(await reads.getRun(own.workspaceId, id)).toMatchObject({
        stage,
        dataset: null,
      });
      expect(await reads.listRunEvents(id, {})).toEqual(before);
    },
  );

  it("rejects backward stage transitions and records a terminal event only once", async () => {
    const own = await seedTrainingTask(db.database);
    const writes = createTrainingRunStore(db.database);
    const reads = createTrainingStore(db.database);
    const id = randomUUID();
    await writes.create(id, own.input);
    await writes.transition(id, "training", 2);
    await writes.transition(id, "building_dataset", 3);
    await Promise.all([
      writes.transition(id, "failed", 4),
      writes.transition(id, "failed", 5),
    ]);

    const events = await reads.listRunEvents(id, {});
    expect(
      events
        .filter((event) => event.payload.type === "stage_entered")
        .map((event) => event.payload),
    ).toEqual([
      { type: "stage_entered", stage: "queued" },
      { type: "stage_entered", stage: "training" },
      { type: "stage_entered", stage: "failed" },
    ]);
    expect(
      events.filter((event) => event.payload.type === "run_finished"),
    ).toHaveLength(1);
    expect(await reads.getRun(own.workspaceId, id)).toMatchObject({
      stage: "failed",
      finishedAt: expect.any(Date),
    });
  });

  it("publishes one adapter and event under concurrent retries, including retries after completion", async () => {
    const own = await seedTrainingTask(db.database);
    const writes = createTrainingRunStore(db.database);
    const reads = createTrainingStore(db.database);
    const id = randomUUID();
    await writes.create(id, own.input);
    await expect(
      writes.publish(id, own.input, trainingAdapter, "available"),
    ).rejects.toThrow("Run is not publishing");
    await writes.transition(id, "publishing");
    await expect(
      writes.publish(
        id,
        own.input,
        { ...trainingAdapter, rank: 0 },
        "available",
      ),
    ).rejects.toMatchObject({ name: "ZodError" });
    expect(await reads.listVersions(own.task.id)).toEqual([]);

    const ids = await Promise.all(
      Array.from({ length: 4 }, () =>
        writes.publish(id, own.input, trainingAdapter, "available"),
      ),
    );
    expect(new Set(ids).size).toBe(1);
    await writes.transition(id, "succeeded");
    expect(
      await writes.publish(id, own.input, trainingAdapter, "available"),
    ).toBe(ids[0]);
    expect(await reads.listVersions(own.task.id)).toHaveLength(1);
    expect(
      (await reads.listRunEvents(id, {})).filter(
        (event) => event.payload.type === "published",
      ),
    ).toHaveLength(1);
  });

  it("allocates distinct version names for runs sharing a task and dataset day", async () => {
    const own = await seedTrainingTask(db.database);
    const writes = createTrainingRunStore(db.database);
    const reads = createTrainingStore(db.database);
    for (let index = 0; index < 2; index++) {
      const id = randomUUID();
      await writes.create(id, own.input);
      await writes.transition(id, "publishing");
      await writes.publish(id, own.input, trainingAdapter, "available");
      await writes.transition(id, "succeeded");
    }

    expect(
      (await reads.listVersions(own.task.id))
        .map((version) => version.name)
        .sort(),
    ).toEqual(["triage-20260930", "triage-20260930-2"]);
  });

  it("rolls back a failed publication without storing an adapter or published event", async () => {
    const own = await seedTrainingTask(db.database);
    const other = await seedTrainingTask(db.database);
    const writes = createTrainingRunStore(db.database);
    const reads = createTrainingStore(db.database);
    const id = randomUUID();
    await writes.create(id, own.input);
    await writes.transition(id, "publishing");
    const before = await reads.listRunEvents(id, {});

    await expect(
      writes.publish(
        id,
        { ...own.input, workspaceId: other.workspaceId },
        trainingAdapter,
        "available",
      ),
    ).rejects.toMatchObject({ cause: { code: "23503" } });
    expect(
      await db.database
        .select()
        .from(taskVersions)
        .where(eq(taskVersions.trainingRunId, id)),
    ).toEqual([]);
    expect(await reads.listRunEvents(id, {})).toEqual(before);
    expect(
      (
        await db.database
          .select()
          .from(trainingRuns)
          .where(eq(trainingRuns.id, id))
      )[0]?.stage,
    ).toBe("publishing");
  });
  it("rolls back the result update if PostgreSQL rejects its event insert", async () => {
    const own = await seedTrainingTask(db.database);
    const writes = createTrainingRunStore(db.database);
    const reads = createTrainingStore(db.database);
    const id = randomUUID();
    await writes.create(id, own.input);
    await db.pool.query(`
      create function reject_dataset_event() returns trigger language plpgsql as $$
      begin
        if new.payload->>'type' = 'dataset_built' then
          raise exception 'Injected event insert failure';
        end if;
        return new;
      end;
      $$;
      create trigger reject_dataset_event before insert on training_run_events
        for each row execute function reject_dataset_event();
    `);

    try {
      await expect(
        writes.result(
          id,
          "dataset",
          dataset,
          { type: "dataset_built", ...dataset },
          1,
        ),
      ).rejects.toMatchObject({ cause: { code: "P0001" } });
      expect(await reads.getRun(own.workspaceId, id)).toMatchObject({
        dataset: null,
      });
      expect(await reads.listRunEvents(id, {})).toHaveLength(2);
    } finally {
      await db.pool.query(
        "drop trigger reject_dataset_event on training_run_events; drop function reject_dataset_event()",
      );
    }
  });

  it("persists evaluation independently of dataset results and ignores evaluation retries", async () => {
    const own = await seedTrainingTask(db.database);
    const writes = createTrainingRunStore(db.database);
    const reads = createTrainingStore(db.database);
    const id = randomUUID();
    const evaluation: RunEvaluation = {
      holdout_groups: 10,
      holdout_examples: 10,
      comparison_model_id: "openai/gpt-5",
      judge_model_id: "openai/gpt-5",
      vs_comparison: {
        comparator_model_id: "openai/gpt-5",
        win: 0.7,
        tie: 0.1,
        loss: 0.2,
        unresolved: 0,
      },
      cost_per_request_nano_usd: { fine_tuned: 100, comparison: 200 },
      output_tokens_per_second: { fine_tuned: 30, comparison: 20 },
      error_rate: 0,
    };
    const payload = {
      type: "evaluation_completed",
      judge: evaluation.judge_model_id,
      groups: 10,
      win: 0.7,
      tie: 0.1,
      loss: 0.2,
      unresolved: 0,
    } as const;
    await writes.create(id, own.input);
    await writes.result(
      id,
      "dataset",
      dataset,
      { type: "dataset_built", ...dataset },
      1,
    );
    await writes.result(id, "evaluation", evaluation, payload, 1);
    await writes.result(
      id,
      "evaluation",
      { ...evaluation, error_rate: 0.5 },
      payload,
      2,
    );

    expect(await reads.getRun(own.workspaceId, id)).toMatchObject({
      dataset,
      evaluation,
    });
    expect(
      (await reads.listRunEvents(id, {})).filter(
        (event) => event.payload.type === "evaluation_completed",
      ),
    ).toHaveLength(1);
  });
});
