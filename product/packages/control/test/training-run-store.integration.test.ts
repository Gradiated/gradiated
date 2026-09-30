import { randomUUID } from "node:crypto";
import type { RunDatasetSummary, RunEvaluation } from "@gradiated/contracts";
import { eq } from "drizzle-orm";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import {
  trainingRuns,
  trainingRunEvents,
  taskVersions,
} from "../src/db/schema/index.js";
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
