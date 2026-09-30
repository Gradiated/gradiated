import {
  ControlServiceError,
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

    return createTemporalTrainingEngine((await connection).client);
  };
  const engine: TrainingEngine = {
    updateSchedule: async (taskId, cron) =>
      (await get()).updateSchedule(taskId, cron),
    start: async (input) => {
      if (environment.TRAINING_EXECUTOR !== "mock")
        throw new TrainingAdmissionError(
          "training_not_configured",
          "Training execution is not enabled.",
        );
      return (await get()).start(input);
    },
    cancel: async (taskId, runId) => (await get()).cancel(taskId, runId),
  };

  return {
    engine,
    close: async () => {
      if (connection) await (await connection).connection.close();
    },
  };
};
