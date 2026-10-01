import { once } from "node:events";
import { fileURLToPath } from "node:url";
import { NativeConnection, Worker } from "@temporalio/worker";
import {
  connectTemporal,
  temporalOptions,
  TRAINING_TASK_QUEUE,
} from "@gradiated/temporal";
import {
  createTrainingArtifacts,
  createTemporalTrainingEngine,
  type TrainingEngine,
  ObjectStorage,
  type ControlDatabase,
  type ContentStore,
} from "@gradiated/control";
import {
  createNomadRequest,
  parseNomadEnvironment,
} from "@gradiated/nomad-pki";
import { createTrainingExecutorActivities } from "./executor-activities.js";
import { trainingConfiguration } from "./configuration.js";
import { createMockTrainingActivities } from "./activities.js";

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
  const configureTrainingExecutor = (engine: TrainingEngine) => {
    const config = trainingConfiguration(input.environment);
    const nomad = parseNomadEnvironment(input.environment);
    if (!nomad) throw new Error("Training requires Nomad credentials.");

    return createTrainingExecutorActivities({
      database: input.database,
      engine,
      contents: input.contents,
      artifacts: createTrainingArtifacts(
        new ObjectStorage(config.TRAINING_ARTIFACTS_BUCKET),
      ),
      nomad: createNomadRequest(nomad),
      podIds: config.TRAINING_POD_IDS,
      token: config.TRAINING_HOST_TOKEN,
      host: {
        bundleUrl: config.TRAINING_BUNDLE_URL,
        bundleSha256: config.TRAINING_BUNDLE_SHA256,
        baseId: config.TRAINING_BASE_ID,
        gpuType: config.TRAINING_GPU_MODEL,
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
      if (!input.signal.aborted)
        await once(input.signal, "abort", { signal: listenerCleanup.signal });
    });
  } finally {
    listenerCleanup.abort();
    await Promise.all([connection.close(), temporal?.connection.close()]);
  }
};
