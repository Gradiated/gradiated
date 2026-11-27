import { createVersionFileStore } from "./version-file-store.js";
import { readWorkloadBenchmarks } from "./workload-benchmarks.js";
import { WORKLOAD_BENCHMARK_FILE } from "@gradiated/contracts";
import type { ObjectStorage } from "../storage/object-storage.js";
import { createReportShares } from "./report-shares.js";
import { createVersionFiles } from "./version-files.js";
import { createModelUploads } from "./uploads.js";
import { catalogModel } from "@gradiated/contracts/model-catalog";
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
import type { AdapterQualifier, QualificationLock } from "./qualification.js";
import { createTrainingRunStore } from "./run-store.js";
import { createTrainingStore } from "./store.js";
import type { TaskVersionRecord } from "./records.js";
import { userActor } from "./production-changes.js";
import type { GradArtifacts } from "./grad.js";
import { createArtifactPublisher } from "./publish.js";
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
  uploadStorage?: ObjectStorage,
  qualifyAdapter?: AdapterQualifier,
  lockQualification?: QualificationLock,
  reportShareSecret?: string,
  artifacts: {
    grad?: GradArtifacts;
    bundles?: Pick<ObjectStorage, "stream" | "uri">;
  } = {},
) => {
  const records = createTrainingStore(database);
  const publisher = createArtifactPublisher({
    database,
    ...artifacts,
    ...(qualifyAdapter ? { qualifyAdapter } : {}),
    ...(lockQualification ? { lockQualification } : {}),
  });

  const member = async (userId: string, workspaceId: string) => {
    const result = await requireWorkspaceMembership(database, {
      userId,
      workspaceId,
    });
    if (result.workspace.archivedAt) throw notFound("workspace");
    return result;
  };

  // Eval-only models are grad's, hidden from the workspace's own model calls.
  const findTask = async (workspaceId: string, name: string) => {
    const task = await records.getTask(workspaceId, name);
    if (!task || task.purpose === "eval") throw notFound("task");

    return task;
  };

  const findVersion = async (taskId: string, reference: string) => {
    const row = await records.findVersion(taskId, reference);
    if (!row) throw notFound("version");

    return row;
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

  const { structure, ...uploads } = createModelUploads(database, uploadStorage);
  const { sharedVersion, ...shares } = createReportShares(
    database,
    uploadStorage,
    reportShareSecret,
  );
  const summarize = (version: TaskVersionRecord) => {
    if (version.adapter.format !== "peft_lora")
      throw new ControlServiceError(
        "not_found",
        "Only LoRA adapters have weights to explore.",
      );
    if (!downloads?.weights)
      throw new ControlServiceError(
        "unavailable",
        "Adapter storage is not configured.",
      );

    return downloads.weights(
      version.adapter.artifact_uri,
      version.trainingRunId ?? version.id,
      version.adapter.size_bytes,
      version.adapter.sha256,
      version.workspaceId,
    );
  };

  return {
    uploads,
    artifacts: publisher,
    files: createVersionFiles(database, uploadStorage),
    shares,
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

      const tasks = (await records.listTasks(workspaceId)).filter(
        (task) => task.purpose === "serving",
      );
      const changed = await Promise.all(
        tasks.map(({ latestRun }) =>
          latestRun ? reconcileTrainingRun(database, engine, latestRun) : false,
        ),
      );
      const current = changed.some(Boolean)
        ? (await records.listTasks(workspaceId)).filter(
            (task) => task.purpose === "serving",
          )
        : tasks;
      const files = await createVersionFileStore(database).listReadyNamed(
        workspaceId,
        current.flatMap((task) =>
          task.latestVersion ? [task.latestVersion.id] : [],
        ),
        WORKLOAD_BENCHMARK_FILE,
      );
      const benchmarks = await readWorkloadBenchmarks(files, uploadStorage);

      return current.map((task) => ({
        ...task,
        workloadBenchmark: task.latestVersion
          ? (benchmarks.get(task.latestVersion.id) ?? null)
          : null,
      }));
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

      const baseModelId = input.base_model_id ?? task.baseModelId;
      const schedule =
        input.training_schedule === undefined
          ? task.trainingSchedule
          : input.training_schedule;
      if (
        schedule &&
        baseModelId &&
        catalogModel(baseModelId) &&
        !TRAINING_BASE_MODELS.some((base) => base.id === baseModelId)
      )
        throw new ControlServiceError(
          "unavailable",
          "The base model is unavailable for training.",
        );

      const preserveSchedule =
        input.base_model_id !== undefined &&
        input.training_schedule === undefined &&
        task.baseModelId &&
        catalogModel(task.baseModelId) &&
        !TRAINING_BASE_MODELS.some((base) => base.id === task.baseModelId);
      const updated = await records.updateTask(
        task.id,
        preserveSchedule ? { ...input, training_schedule: schedule } : input,
      );
      if (engine || input.training_schedule !== undefined) {
        try {
          if (!engine) throw new Error("Training engine unavailable");

          await engine.updateSchedule(updated.id, updated.trainingSchedule);
          // Workspace cleanup may have deleted the schedule while this update
          // was in flight; remove a schedule recreated for a deleted task.
          if (
            updated.trainingSchedule &&
            !(await records.isTaskLive(updated.id))
          )
            await engine.updateSchedule(updated.id, null);
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
      const version = await findVersion(task.id, versionId);
      if (!downloads?.results)
        throw new ControlServiceError(
          "unavailable",
          "Evaluation storage is not configured.",
        );

      if (!version.trainingRunId) throw notFound("evaluation");

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
      const version = await findVersion(task.id, versionId);
      if (!downloads)
        throw new ControlServiceError(
          "unavailable",
          "Adapter storage is not configured.",
        );

      return downloads.sign(
        version.adapter.artifact_uri,
        version.trainingRunId ?? version.id,
        version.adapter.size_bytes,
        version.adapter.sha256,
        version.workspaceId,
      );
    },

    async adapterWeights(
      userId: string,
      workspaceId: string,
      name: string,
      versionId: string,
    ) {
      await member(userId, workspaceId);
      const task = await findTask(workspaceId, name);
      return summarize(await findVersion(task.id, versionId));
    },

    async sharedAdapterWeights(versionId: string, signature: string) {
      const { version } = await sharedVersion(versionId, signature);
      return summarize(version);
    },

    async sharedAdapterConfiguration(versionId: string, signature: string) {
      const { version } = await sharedVersion(versionId, signature);
      return structure(version.baseModelId);
    },

    async getVersion(
      userId: string,
      workspaceId: string,
      name: string,
      version: string,
    ) {
      await member(userId, workspaceId);
      const task = await findTask(workspaceId, name);

      return { task, version: await findVersion(task.id, version) };
    },

    async listProductionChanges(
      userId: string,
      workspaceId: string,
      name: string,
    ) {
      await member(userId, workspaceId);
      const task = await findTask(workspaceId, name);

      return records.listProductionChanges(task.id);
    },

    async promote(
      userId: string,
      workspaceId: string,
      name: string,
      versionNameOrId: string,
    ) {
      await requireWorkspaceEditor(database, { userId, workspaceId });
      const task = await findTask(workspaceId, name);
      const version = await findVersion(task.id, versionNameOrId);
      requireLoadableAdapter(version);
      // A cartridge is qualified on every promotion, so it never becomes production without capacity.
      if (
        version.status === "available" &&
        version.adapter.format !== "cartridge"
      )
        return records.setProductionVersion(
          task.id,
          version.id,
          userActor(userId),
        );

      if (!qualifyAdapter)
        throw new ControlServiceError(
          "unavailable",
          "Serving qualification is unavailable. The version was not promoted.",
        );

      const release = lockQualification
        ? await lockQualification(version.id)
        : async () => undefined;
      if (!release)
        throw new ControlServiceError(
          "conflict",
          "This version is already being tested for serving. Try again in a few minutes.",
        );

      let promoted: Awaited<ReturnType<typeof records.promoteQualifiedVersion>>;
      try {
        await qualifyAdapter(version);
        promoted = await records.promoteQualifiedVersion(
          task.id,
          version.id,
          {
            productionVersionId: task.productionVersionId,
            updatedAt: task.updatedAt,
          },
          userActor(userId),
        );
      } finally {
        await release().catch(() => undefined);
      }
      if (promoted === "not_found") throw notFound("version");
      if (promoted === "stale")
        throw new ControlServiceError(
          "conflict",
          "This model changed while the version was being tested. The version can now serve; promote it again to make it production.",
        );

      return promoted;
    },
  };
};
