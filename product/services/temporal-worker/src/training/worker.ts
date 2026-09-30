import { once } from "node:events";
import { fileURLToPath } from "node:url";
import { NativeConnection, Worker } from "@temporalio/worker";
import { temporalOptions, TRAINING_TASK_QUEUE } from "@gradiated/temporal";
import { type ControlDatabase, type ContentStore } from "@gradiated/control";
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
  const connection = await NativeConnection.connect(options);
  const listenerCleanup = new AbortController();

  try {
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
      activities: createMockTrainingActivities(input.database, input.contents),
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
    await connection.close();
  }
};
