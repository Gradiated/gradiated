import {
  ControlServiceError,
  validateSftInput,
  TrainingAdmissionError,
  createTemporalTrainingEngine,
  type TrainingEngine,
} from "@gradiated/control";
import { connectTemporal } from "@gradiated/temporal";

export const createTrainingEngine = (environment: NodeJS.ProcessEnv) => {
  let connection: ReturnType<typeof connectTemporal> | undefined;
  const get = async () => {
    connection ??= connectTemporal(environment).catch((error: unknown) => {
      connection = undefined;
      throw new ControlServiceError(
        "unavailable",
        "Training is unavailable.",
        error,
      );
    });

    return createTemporalTrainingEngine(
      (await connection).client,
      environment.TRAINING_EXECUTOR === "qwen-sft"
        ? "trainingRunV2"
        : "trainingRunV1",
      environment.TRAINING_EXECUTOR === "qwen-sft"
        ? "trainingRunV2"
        : "trainingTaskV1",
    );
  };
  const engine: TrainingEngine = {
    updateSchedule: async (taskId, cron) =>
      (await get()).updateSchedule(taskId, cron),
    start: async (input) => {
      if (!["mock", "qwen-sft"].includes(environment.TRAINING_EXECUTOR ?? ""))
        throw new TrainingAdmissionError(
          "training_not_configured",
          "Training execution is not enabled.",
        );
      if (environment.TRAINING_EXECUTOR === "qwen-sft") validateSftInput(input);
      return (await get()).start(input);
    },
    status: async (workflowId, runId) =>
      (await get()).status(workflowId, runId),
    cancel: async (taskId, runId, workflowId) =>
      (await get()).cancel(taskId, runId, workflowId),
  };

  return {
    engine,
    close: async () => {
      if (connection) await (await connection).connection.close();
    },
  };
};
