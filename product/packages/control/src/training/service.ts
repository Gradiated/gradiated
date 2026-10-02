import {
  TRAINING_BASE_MODELS,
  type UpdateTask,
  type TrainingRunListQuery,
} from "@gradiated/contracts";
import {
  requireWorkspaceEditor,
  requireWorkspaceMembership,
} from "../access.js";
import type { ControlDatabase } from "../db/client.js";
import { ControlServiceError } from "../errors.js";
import type { ContentStore } from "../traces/storage.js";
import { reconcileTrainingRun } from "./engine.js";
import { prepareTraining } from "./admission.js";
import type { AdapterDownloads } from "./downloads.js";
import { requireLoadableAdapter } from "./hosting.js";
import { createTrainingRunStore } from "./run-store.js";
import { createTrainingStore } from "./store.js";
import { TrainingAdmissionError, type TrainingEngine } from "./types.js";

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
  validateEvaluationModel?: (id: string) => Promise<void>,
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

    if (await reconcileTrainingRun(database, engine, row)) {
      const refreshed = await records.getRun(workspaceId, runId);
      if (!refreshed) throw notFound("training run");

      return refreshed;
    }

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
        executor,
      );

      const id = await executor.start(input);
      const created = await createTrainingRunStore(database).create(id, input);
      if (!created)
        throw new TrainingAdmissionError(
          "already_training",
          "Already training.",
        );

      return { id };
    },

    async cancelRun(userId: string, workspaceId: string, runId: string) {
      await requireWorkspaceEditor(database, { userId, workspaceId });
      const run = await findRun(workspaceId, runId);
      if (run.finishedAt) return;

      await requireEngine().cancel(
        run.taskId,
        runId,
        run.workflowId ?? undefined,
      );
      await createTrainingRunStore(database).requestCancellation(runId, userId);
    },

    async listTasks(userId: string, workspaceId: string) {
      await member(userId, workspaceId);

      const tasks = await records.listTasks(workspaceId);
      const changed = await Promise.all(
        tasks.map(({ latestRun }) =>
          latestRun ? reconcileTrainingRun(database, engine, latestRun) : false,
        ),
      );
      return changed.some(Boolean) ? records.listTasks(workspaceId) : tasks;
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

      for (const id of [input.comparison_model_id, input.judge_model_id]) {
        if (id !== undefined) await validateEvaluationModel?.(id);
      }

      if (input.base_model_id !== undefined) {
        const model = await records.getModel(input.base_model_id);
        if (!model) throw notFound("base model");
        if (
          model.status !== "available" &&
          !TRAINING_BASE_MODELS.some((base) => base.id === model.id)
        )
          throw new ControlServiceError(
            "unavailable",
            "The base model is unavailable.",
          );
      }

      const updated = await records.updateTask(task.id, input);
      if (engine || input.training_schedule !== undefined) {
        try {
          if (!engine) throw new Error("Training engine unavailable");

          await engine.updateSchedule(updated.id, updated.trainingSchedule);
        } catch {
          throw new ControlServiceError(
            "unavailable",
            "The schedule was saved, but automatic training could not be updated. Retry saving the schedule.",
          );
        }
      }

      return updated;
    },

    async listRuns(
      userId: string,
      workspaceId: string,
      filters: TrainingRunListQuery = {},
    ) {
      await member(userId, workspaceId);
      const runs = await records.listRuns(workspaceId, filters);
      const changed = await Promise.all(
        runs.map((run) => reconcileTrainingRun(database, engine, run)),
      );
      return changed.some(Boolean)
        ? records.listRuns(workspaceId, filters)
        : runs;
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

    async evaluationResults(
      userId: string,
      workspaceId: string,
      name: string,
      versionId: string,
    ) {
      await member(userId, workspaceId);
      const task = await findTask(workspaceId, name);
      const version = await records.getVersion(task.id, versionId);
      if (!version) throw notFound("version");
      if (!downloads?.results)
        throw new ControlServiceError(
          "unavailable",
          "Evaluation storage is not configured.",
        );

      return downloads.results(version.trainingRunId);
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

      requireLoadableAdapter(version);

      return records.setProductionVersion(task.id, version.id);
    },
  };
};
