import { createHash } from "node:crypto";
import { Context } from "@temporalio/activity";
import type { RunStage, TaskVersionAdapter } from "@gradiated/contracts";
import {
  createTrainingRunStore,
  prepareTraining,
  TrainingAdmissionError,
  ControlServiceError,
  type TrainingInput,
  type ControlDatabase,
  type ContentStore,
} from "@gradiated/control";

const withHeartbeat = async <T>(operation: () => Promise<T>): Promise<T> => {
  const context = Context.current();
  context.heartbeat();
  const timer = setInterval(() => context.heartbeat(), 5_000);
  try {
    context.cancellationSignal.throwIfAborted();
    const result = await operation();
    context.cancellationSignal.throwIfAborted();

    return result;
  } finally {
    clearInterval(timer);
  }
};

export const createMockTrainingActivities = (
  database: ControlDatabase,
  contents: ContentStore,
) => {
  const store = createTrainingRunStore(database);
  const digest = createHash("sha256")
    .update("mock-training-artifact")
    .digest("hex");

  return {
    createRun: (runId: string, input: TrainingInput) =>
      store.create(runId, input),
    enterStage: (runId: string, stage: RunStage) =>
      store.transition(runId, stage, Context.current().info.attempt),
    finishRun: (runId: string, stage: "succeeded" | "failed" | "cancelled") =>
      store.transition(runId, stage, Context.current().info.attempt),
    async buildDataset(runId: string, input: TrainingInput) {
      Context.current().heartbeat();
      const dataset = {
        oldest_trace_at: input.inputCutoff,
        newest_trace_at: input.inputCutoff,
        eligible_examples: 0,
        duplicates_removed: 0,
        train: 0,
        validation: 0,
        test: 0,
      };
      await store.result(
        runId,
        "dataset",
        dataset,
        { type: "dataset_built", ...dataset },
        Context.current().info.attempt,
      );
    },
    async allocateHost(runId: string, _input: TrainingInput) {
      Context.current().heartbeat();

      return { id: `mock-${runId}` };
    },
    async train(
      runId: string,
      _input: TrainingInput,
      _host: { id: string },
    ): Promise<TaskVersionAdapter> {
      for (let tick = 0; tick < 5; tick++) {
        Context.current().heartbeat({ tick });
        await Context.current().sleep(1000);
      }

      return {
        format: "peft_lora",
        artifact_uri: `s3://mock-training/runs/${runId}/adapter`,
        sha256: digest,
        size_bytes: 0,
        rank: 1,
      };
    },
    async verify(
      _runId: string,
      _adapter: TaskVersionAdapter,
      _host: { id: string },
    ) {
      Context.current().heartbeat();
    },
    async publish(
      runId: string,
      input: TrainingInput,
      adapter: TaskVersionAdapter,
    ) {
      Context.current().heartbeat();
      await store.publish(runId, input, adapter, "unavailable");
    },
    async evaluate(
      _runId: string,
      _input: TrainingInput,
      _host: { id: string },
    ) {
      Context.current().heartbeat();
    },
    async releaseHost(_runId: string) {
      Context.current().heartbeat();
    },
    prepareRun: (taskId: string) =>
      withHeartbeat(async () => {
        try {
          return await prepareTraining(
            database,
            contents,
            taskId,
            "automation",
            null,
          );
        } catch (error) {
          if (
            error instanceof TrainingAdmissionError ||
            (error instanceof ControlServiceError && error.code === "not_found")
          )
            return null;
          throw error;
        }
      }),
  };
};

export type TrainingActivities = ReturnType<
  typeof createMockTrainingActivities
>;
