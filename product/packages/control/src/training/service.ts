import type { UpdateTask, TrainingRunListQuery } from "@gradiated/contracts";
import {
  requireWorkspaceEditor,
  requireWorkspaceMembership,
} from "../access.js";
import type { ControlDatabase } from "../db/client.js";
import { ControlServiceError } from "../errors.js";
import type { ContentStore } from "../traces/storage.js";
import { prepareTraining } from "./admission.js";
import type { AdapterDownloads } from "./downloads.js";
import { createTrainingRunStore } from "./run-store.js";
import { createTrainingStore } from "./store.js";
import type { TrainingEngine } from "./types.js";

export type {
  TaskRecord,
  TaskVersionRecord,
  TrainingRunRecord,
} from "./records.js";

export type TrainingService = ReturnType<typeof createTrainingService>;

const notFound = (thing: string) =>
  new ControlServiceError("not_found", `The ${thing} was not found.`);

export const createTrainingService = (
  database: ControlDatabase,
  store: ContentStore,
  downloads?: AdapterDownloads,
  engine?: TrainingEngine,
) => {
  const records = createTrainingStore(database);

  const member = async (userId: string, workspaceId: string) => {
    const result = await requireWorkspaceMembership(database, {
      userId,
      workspaceId,
    });
    if (result.workspace.archivedAt) throw notFound("workspace");
    return result;
  };

  const findTask = async (workspaceId: string, name: string) => {
    const task = await records.getTask(workspaceId, name);
    if (!task) throw notFound("task");

    return task;
  };

  const findRun = async (workspaceId: string, runId: string) => {
    const row = await records.getRun(workspaceId, runId);
    if (!row) throw notFound("training run");

    return row;
  };

  const requireEngine = () => {
    if (!engine)
      throw new ControlServiceError("unavailable", "Training is unavailable.");

    return engine;
  };

  return {
    async startRun(userId: string, workspaceId: string, taskId: string) {
      await requireWorkspaceEditor(database, { userId, workspaceId });
      const task = await records.getTaskById(workspaceId, taskId);
      if (!task) throw notFound("task");

      const executor = requireEngine();
      const input = await prepareTraining(
        database,
        store,
        task.id,
        "manual",
        userId,
      );

      const id = await executor.start(input);
      await createTrainingRunStore(database).create(id, input);

      return { id };
    },

    async cancelRun(userId: string, workspaceId: string, runId: string) {
      await requireWorkspaceEditor(database, { userId, workspaceId });
      const run = await findRun(workspaceId, runId);
      if (run.finishedAt) return;

      await requireEngine().cancel(run.taskId, runId);
      await createTrainingRunStore(database).requestCancellation(runId, userId);
    },

    async listTasks(userId: string, workspaceId: string) {
      await member(userId, workspaceId);

      return records.listTasks(workspaceId);
    },

    async getTask(userId: string, workspaceId: string, name: string) {
      await member(userId, workspaceId);

      return findTask(workspaceId, name);
    },

    async updateTask(
      userId: string,
      workspaceId: string,
      name: string,
      input: UpdateTask,
    ) {
      await requireWorkspaceEditor(database, { userId, workspaceId });
      const task = await findTask(workspaceId, name);
      if (input.base_model_id !== undefined) {
        const model = await records.getModel(input.base_model_id);
        if (!model) throw notFound("base model");
        if (model.status !== "available")
          throw new ControlServiceError(
            "unavailable",
            "The base model is unavailable.",
          );
      }

      const updated = await records.updateTask(task.id, input);
      try {
        await engine?.updateSchedule(updated.id, updated.trainingSchedule);
      } catch (error) {
        console.warn(
          JSON.stringify({
            event: "training_schedule_update_failed",
            task_id: updated.id,
            error_name: error instanceof Error ? error.name : "UnknownError",
          }),
        );
      }

      return updated;
    },

    async listRuns(
      userId: string,
      workspaceId: string,
      filters: TrainingRunListQuery = {},
    ) {
      await member(userId, workspaceId);
      return records.listRuns(workspaceId, filters);
    },

    async getRun(userId: string, workspaceId: string, runId: string) {
      await member(userId, workspaceId);

      return findRun(workspaceId, runId);
    },

    async listRunEvents(
      userId: string,
      workspaceId: string,
      runId: string,
      page: { after?: number | undefined; limit: number },
    ) {
      await member(userId, workspaceId);
      await findRun(workspaceId, runId);

      return records.listRunEvents(runId, page);
    },

    async listVersions(userId: string, workspaceId: string, name: string) {
      await member(userId, workspaceId);
      const task = await findTask(workspaceId, name);
      const versions = await records.listVersions(task.id);

      return { task, versions };
    },

    async downloadAdapter(
      userId: string,
      workspaceId: string,
      name: string,
      versionId: string,
    ) {
      await member(userId, workspaceId);
      const task = await findTask(workspaceId, name);
      const version = await records.getVersion(task.id, versionId);
      if (!version) throw notFound("version");
      if (!downloads)
        throw new ControlServiceError(
          "unavailable",
          "Adapter storage is not configured.",
        );

      return downloads.sign(
        version.adapter.artifact_uri,
        version.trainingRunId,
        version.adapter.size_bytes,
        version.adapter.sha256,
      );
    },

    async promote(
      userId: string,
      workspaceId: string,
      name: string,
      versionId: string,
    ) {
      await requireWorkspaceEditor(database, { userId, workspaceId });
      const task = await findTask(workspaceId, name);
      const version = await records.getVersion(task.id, versionId);
      if (!version) throw notFound("version");
      if (version.status !== "available")
        throw new ControlServiceError(
          "unavailable",
          "Serving is not enabled for this version.",
        );

      return records.setProductionVersion(task.id, version.id);
    },
  };
};
