import {
  TRAINING_TASK_QUEUE,
  TRAINING_WORKFLOW,
  trainingWorkflowId,
  WorkflowExecutionAlreadyStartedError,
  WorkflowIdReusePolicy,
  WorkflowNotFoundError,
  type Client,
} from "@gradiated/temporal";
import { updateTrainingSchedule } from "./schedules.js";
import { ControlServiceError } from "../errors.js";
import { TrainingAdmissionError, type TrainingEngine } from "./types.js";

export const createTemporalTrainingEngine = (
  client: Client,
): TrainingEngine => ({
  updateSchedule: (taskId, cron) =>
    updateTrainingSchedule(client, taskId, cron),
  async start(input) {
    try {
      const handle = await client.workflow.start(TRAINING_WORKFLOW, {
        workflowId: trainingWorkflowId(input.taskId),
        taskQueue: TRAINING_TASK_QUEUE,
        args: [input],
        workflowIdReusePolicy: WorkflowIdReusePolicy.ALLOW_DUPLICATE,
        workflowTaskTimeout: "30 seconds",
      });

      return handle.firstExecutionRunId;
    } catch (error) {
      if (error instanceof WorkflowExecutionAlreadyStartedError)
        throw new TrainingAdmissionError(
          "already_training",
          "Already training.",
        );
      throw new ControlServiceError(
        "unavailable",
        "Could not start training.",
        error,
      );
    }
  },
  async cancel(taskId, runId) {
    try {
      await client.workflow
        .getHandle(trainingWorkflowId(taskId), runId)
        .cancel();
    } catch (error) {
      if (error instanceof WorkflowNotFoundError)
        throw new ControlServiceError(
          "not_found",
          "The training workflow was not found.",
        );
      throw new ControlServiceError(
        "unavailable",
        "Could not cancel training.",
        error,
      );
    }
  },
});
