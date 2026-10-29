import {
  MODEL_CATALOG,
  type CatalogEntry,
} from "@gradiated/contracts/model-catalog";
import type { ControlDatabase } from "../db/client.js";
import type { ContentStore } from "../traces/storage.js";
import { createTrainingStore } from "./store.js";
import type { TrainingEngine } from "./types.js";

// Upload grants last two hours; a workflow times out after 24 hours.
const FINISHED_GRACE_MILLISECONDS = 3 * 60 * 60 * 1000;
const ABANDONED_AFTER_MILLISECONDS = 48 * 60 * 60 * 1000;

export const createTrainingArtifactCleanup = (
  database: ControlDatabase,
  objects: ContentStore,
  now: () => Date = () => new Date(),
) => {
  const store = createTrainingStore(database);

  return async () => {
    const at = now().getTime();
    // Artifact keys carry no workspace, so the run row must outlive its objects.
    const runId = await store.archivedRunToDelete(
      new Date(at - FINISHED_GRACE_MILLISECONDS),
      new Date(at - ABANDONED_AFTER_MILLISECONDS),
    );
    if (!runId) return;

    const page = await objects.list(`runs/${runId}/`, { limit: 1000 });
    if (page.keys.length) {
      await objects.delete(page.keys);
      return;
    }

    await store.deleteRun(runId);
  };
};

export const deleteArchivedTasks = async (
  database: ControlDatabase,
  engine: Pick<TrainingEngine, "updateSchedule">,
) => {
  const store = createTrainingStore(database);
  const errors: unknown[] = [];

  for (const taskId of await store.archivedTasksWithoutRuns(100)) {
    try {
      await engine.updateSchedule(taskId, null);
      await store.deleteTaskWithoutRuns(taskId);
    } catch (error) {
      errors.push(error);
    }
  }

  if (errors.length === 1) throw errors[0];
  if (errors.length) throw new AggregateError(errors, "Task cleanup failed.");
};

export const deleteRetiredTrainingSchedules = async (
  database: ControlDatabase,
  engine: Pick<TrainingEngine, "updateSchedule">,
) => {
  const retired = (MODEL_CATALOG as readonly CatalogEntry[])
    .filter(
      (model) => model.training && !model.supportedUses.includes("training"),
    )
    .map((model) => model.id);
  if (!retired.length) return;

  const store = createTrainingStore(database);
  const errors: unknown[] = [];
  let cursor: string | undefined;
  for (;;) {
    const ids = await store.tasksForTrainingBases(retired, cursor);
    for (const id of ids) {
      try {
        await engine.updateSchedule(id, null);
        const current = await store.admissionContext(id);
        if (
          current?.task.trainingSchedule &&
          current.task.baseModelId &&
          !retired.includes(current.task.baseModelId) &&
          !current.workspace.archivedAt
        )
          await engine.updateSchedule(id, current.task.trainingSchedule);
      } catch (error) {
        errors.push(error);
      }
    }
    if (ids.length < 100) break;
    cursor = ids.at(-1);
  }
  if (errors.length)
    throw new AggregateError(
      errors,
      "Retired training schedule cleanup failed.",
    );
};
