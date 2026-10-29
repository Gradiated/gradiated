import { once } from "node:events";
import { setTimeout } from "node:timers/promises";
import { fileURLToPath } from "node:url";
import { NativeConnection, Worker } from "@temporalio/worker";
import {
  connectTemporal,
  temporalOptions,
  TRAINING_TASK_QUEUE,
} from "@gradiated/temporal";
import {
  createTrainingArtifacts,
  createCatalogService,
  createTrainingRunStore,
  createTemporalTrainingEngine,
  type TrainingEngine,
  ObjectStorage,
  deleteArchivedTasks,
  deleteRetiredTrainingSchedules,
  type ControlDatabase,
  type ContentStore,
} from "@gradiated/control";
import { createKubernetesRequest } from "@gradiated/control";
import { createTrainingExecutorActivities } from "./executor-activities.js";
import { trainingConfiguration } from "./configuration.js";
import { createMockTrainingActivities } from "./activities.js";
import { createEvaluationModels } from "./evaluation-models.js";
import { createEvaluationPricing } from "./evaluation-pricing.js";
import { stopClosedTrainingJobs } from "./cleanup.js";

export const runTrainingWorker = async (input: {
  database: ControlDatabase;
  contents: ContentStore;
  environment: NodeJS.ProcessEnv;
  signal: AbortSignal;
  onReady: () => Promise<void>;
}) => {
  const { namespace, dataConverter, ...options } = await temporalOptions(
    input.environment,
  );
  const useTrainingExecutor =
    input.environment.TRAINING_EXECUTOR === "qwen-sft";
  const activities = createMockTrainingActivities(
    input.database,
    input.contents,
    !useTrainingExecutor,
  );
  let cleanUpJobs: (() => Promise<void>) | undefined;
  const configureTrainingExecutor = (engine: TrainingEngine) => {
    const config = trainingConfiguration(input.environment);
    const request = createKubernetesRequest(input.signal);
    cleanUpJobs = async () => {
      const results = await Promise.allSettled([
        stopClosedTrainingJobs({
          request,
          engine,
          readRun: createTrainingRunStore(input.database).get,
        }),
        deleteArchivedTasks(input.database, engine),
        deleteRetiredTrainingSchedules(input.database, engine),
      ]);
      const failed = results.find((result) => result.status === "rejected");
      if (failed) throw failed.reason;
    };

    return createTrainingExecutorActivities({
      database: input.database,
      evaluationModels: createEvaluationModels(input.environment),
      evaluationPricing: createEvaluationPricing(
        createCatalogService(input.database),
      ),
      engine,
      contents: input.contents,
      artifacts: createTrainingArtifacts(
        new ObjectStorage(config.TRAINING_ARTIFACTS_BUCKET),
      ),
      request,
      podIds: config.TRAINING_POD_IDS,
      host: {
        bundleUrl: config.TRAINING_BUNDLE_URL,
        bundleSha256: config.TRAINING_BUNDLE_SHA256,
        baseId: config.TRAINING_BASE_ID,
        gpuType: config.TRAINING_GPU_MODEL,
        nodePool: config.TRAINING_NODE_POOL,
      },
    });
  };
  const connection = await NativeConnection.connect(options);
  const listenerCleanup = new AbortController();
  let temporal: Awaited<ReturnType<typeof connectTemporal>> | undefined;

  try {
    if (useTrainingExecutor)
      temporal = await connectTemporal(input.environment);
    const registered = {
      ...activities,
      ...(temporal
        ? configureTrainingExecutor(
            createTemporalTrainingEngine(temporal.client),
          )
        : {}),
    };
    const worker = await Worker.create({
      connection,
      namespace,
      taskQueue: TRAINING_TASK_QUEUE,
      dataConverter,
      workflowsPath: fileURLToPath(
        new URL(
          import.meta.url.endsWith(".ts") ? "./workflows.ts" : "./workflows.js",
          import.meta.url,
        ),
      ),
      activities: registered,
      shutdownGraceTime: "15 seconds",
      shutdownForceTime: "20 seconds",
      maxConcurrentActivityTaskExecutions: 10,
    });

    await worker.runUntil(async () => {
      if (input.signal.aborted) return;

      await input.onReady();
      if (cleanUpJobs) {
        while (!input.signal.aborted) {
          try {
            await cleanUpJobs();
          } catch {
            console.warn("Could not clean up training jobs or schedules.");
          }

          try {
            await setTimeout(60_000, undefined, { signal: input.signal });
          } catch (error) {
            if (!input.signal.aborted) throw error;
          }
        }
        return;
      }

      if (!input.signal.aborted)
        await once(input.signal, "abort", { signal: listenerCleanup.signal });
    });
  } finally {
    listenerCleanup.abort();
    await Promise.all([connection.close(), temporal?.connection.close()]);
  }
};
