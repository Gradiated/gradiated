import { randomUUID } from "node:crypto";
import { Context } from "@temporalio/activity";
import { eq } from "drizzle-orm";
import { afterAll, beforeAll, describe, expect, it, vi } from "vitest";
import { TRAINING_RECIPE } from "@gradiated/contracts";
import {
  type TrainingArtifacts,
  type TrainingEngine,
  createTrainingService,
} from "@gradiated/control";
import { taskVersions, trainingRuns } from "@gradiated/control/schema";
import { createMemoryContentStore } from "../../../packages/control/test/support/content-store.js";
import {
  createTestDatabase,
  type TestDatabase,
} from "../../../packages/control/test/support/postgres.js";
import { seedTrainingTask } from "../../../packages/control/test/support/training.js";
import { createTrainingExecutorActivities } from "../src/training/executor-activities.js";

const artifact = {
  key: "adapter.tar.gz",
  sha256: "a".repeat(64),
  size_bytes: 1024,
};

describe("serving metadata publication", () => {
  let db: TestDatabase;
  beforeAll(async () => {
    db = await createTestDatabase();
  });
  afterAll(() => db.dispose());

  it.each([true, false])(
    "uses the frozen base revision and rejects a changed rank: matching=%s",
    async (matching) => {
      const owner = await seedTrainingTask(db.database);
      const runId = randomUUID();
      await db.database.insert(trainingRuns).values({
        id: runId,
        taskId: owner.task.id,
        trigger: "manual",
        stage: "publishing",
        baseModelId: owner.input.baseModelId,
        inputCutoff: new Date(owner.input.inputCutoff),
      });
      const manifest = {
        train: artifact,
        validation: artifact,
        evaluation: artifact,
        host: {
          bundleUrl: "test",
          bundleSha256: "a".repeat(64),
          baseId: "test",
          gpuType: "B300",
        },
        recipe: {
          ...TRAINING_RECIPE,
          revision: "frozen-training-revision",
          rank: 2,
        },
      };
      const read = vi.fn(async () => Buffer.from(JSON.stringify(manifest)));
      const artifacts = {
        read,
        verify: vi.fn(async () => undefined),
        uri: (key: string) => `s3://bucket/${key}`,
      } as unknown as TrainingArtifacts;
      const activities = createTrainingExecutorActivities({
        database: db.database,
        engine: {} as TrainingEngine,
        contents: createMemoryContentStore(new Map()),
        artifacts,
        nomad: vi.fn(),
        podIds: [],
        host: manifest.host,
        token: "test",
      });
      const current = vi.spyOn(Context, "current").mockReturnValue({
        heartbeat: vi.fn(),
        cancellationSignal: new AbortController().signal,
      } as unknown as Context);
      try {
        const result = activities.publishAdapter(
          runId,
          owner.input,
          { ...artifact, key: `runs/${runId}/adapter.tar.gz` },
          matching ? 2 : 8,
        );
        if (matching) {
          const id = await result;
          const [version] = await db.database
            .select()
            .from(taskVersions)
            .where(eq(taskVersions.id, id));
          expect(version!.adapter).toMatchObject({
            base_model_revision: "frozen-training-revision",
            rank: 2,
            sha256: artifact.sha256,
          });
          expect(version!.status).toBe("available");
          const promoted = await createTrainingService(
            db.database,
            createMemoryContentStore(new Map()),
          ).promote(owner.userId, owner.workspaceId, owner.task.name, id);
          expect(promoted.productionVersionId).toBe(id);
        } else {
          await expect(result).rejects.toThrow("Adapter rank differs");
          expect(
            await db.database
              .select()
              .from(taskVersions)
              .where(eq(taskVersions.trainingRunId, runId)),
          ).toEqual([]);
        }
        expect(read).toHaveBeenCalledWith(`runs/${runId}/run-manifest.json`);
      } finally {
        current.mockRestore();
      }
    },
  );
});
