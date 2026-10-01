import { randomUUID } from "node:crypto";
import { afterAll, beforeAll, expect, it } from "vitest";
import { createTestDatabase, type TestDatabase } from "./support/postgres.js";
import { seedMember, modelInput } from "./support/fixtures.js";
import { createCatalogService } from "../src/catalog/service.js";
import {
  tasks,
  trainingRuns,
  trainingRunEvents,
} from "../src/db/schema/index.js";
import { readTrainingMetrics } from "../src/training/metrics.js";

let db: TestDatabase;
beforeAll(async () => {
  db = await createTestDatabase();
});
afterAll(() => db.dispose());

it("measures live capacity waits and completed stage duration from persisted events", async () => {
  const member = await seedMember(db.database, { role: "owner" });
  const model = modelInput();
  await createCatalogService(db.database).upsertModel(model);
  const taskId = randomUUID();
  await db.database
    .insert(tasks)
    .values({ id: taskId, workspaceId: member.workspaceId, name: "metrics" });
  const now = Date.now();
  const at = (seconds: number) => new Date(now - seconds * 1000);
  const pending = randomUUID();
  const complete = randomUUID();
  for (const [id, stage, finishedAt] of [
    [pending, "awaiting_capacity", null],
    [complete, "succeeded", at(10)],
  ] as const) {
    await db.database.insert(trainingRuns).values({
      id,
      taskId,
      stage,
      trigger: "manual",
      baseModelId: model.id,
      inputCutoff: at(600),
      createdAt: at(600),
      finishedAt,
    });
  }
  for (const [runId, stage, seconds] of [
    [pending, "awaiting_capacity", 120],
    [complete, "awaiting_capacity", 300],
    [complete, "training", 240],
    [complete, "succeeded", 10],
  ] as const) {
    await db.database.insert(trainingRunEvents).values({
      runId,
      source: "worker",
      attempt: 1,
      at: at(seconds),
      payload: { type: "stage_entered", stage },
    });
  }
  const rows = await readTrainingMetrics(db.database);
  expect(rows).toContainEqual({
    kind: "active",
    stage: "awaiting_capacity",
    value: 1,
  });
  expect(rows).toContainEqual({
    kind: "completed",
    stage: "succeeded",
    value: 1,
  });
  expect(rows).toContainEqual({
    kind: "duration",
    stage: "awaiting_capacity",
    value: 60,
  });
  const oldest = rows.find(
    (row) => row.kind === "oldest" && row.stage === "awaiting_capacity",
  )!.value;
  expect(oldest).toBeGreaterThanOrEqual(120);
  expect(oldest).toBeLessThan(130);
});
