import {
  TRAINING_TASK_QUEUE,
  TRAINING_WORKFLOW,
  TRAINING_TASK_WORKFLOW,
  trainingWorkflowId,
  WorkflowExecutionAlreadyStartedError,
  WorkflowIdReusePolicy,
  WorkflowNotFoundError,
  type Client,
} from "@gradiated/temporal";
import type { ControlDatabase } from "../db/client.js";
import type { TrainingRunRecord } from "./records.js";
import { createTrainingRunStore } from "./run-store.js";
import { updateTrainingSchedule } from "./schedules.js";
import { ControlServiceError } from "../errors.js";
import { TrainingAdmissionError, type TrainingEngine } from "./types.js";

export const createTemporalTrainingEngine = (
  client: Client,
  workflowType = TRAINING_WORKFLOW,
  taskWorkflowType = TRAINING_TASK_WORKFLOW,
): TrainingEngine => ({
  updateSchedule: (taskId, cron) =>
    updateTrainingSchedule(client, taskId, cron, taskWorkflowType),
  async start(input) {
    try {
      const handle = await client.workflow.start(workflowType, {
        workflowId: trainingWorkflowId(input.taskId),
        taskQueue: TRAINING_TASK_QUEUE,
        args: [input],
        workflowIdReusePolicy: WorkflowIdReusePolicy.ALLOW_DUPLICATE,
        workflowTaskTimeout: "30 seconds",
        workflowExecutionTimeout: "24 hours",
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
  async status(workflowId, runId) {
    try {
      const execution = await client.workflow
        .getHandle(workflowId, runId)
        .describe();
      switch (execution.status.name) {
        case "RUNNING":
        case "CONTINUED_AS_NEW":
          return "running";
        case "COMPLETED":
          return "succeeded";
        case "CANCELLED":
          return "cancelled";
        case "FAILED":
        case "TERMINATED":
        case "TIMED_OUT":
          return "failed";
        default:
          throw new Error("Unknown training workflow status.");
      }
    } catch (error) {
      if (error instanceof WorkflowNotFoundError) return "failed";
      throw error;
    }
  },
  async cancel(taskId, runId, workflowId = trainingWorkflowId(taskId)) {
    try {
      await client.workflow.getHandle(workflowId, runId).cancel();
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

export const reconcileTrainingRun = async (
  database: ControlDatabase,
  engine: TrainingEngine | undefined,
  run: Pick<
    TrainingRunRecord,
    "id" | "taskId" | "workflowId" | "stage" | "finishedAt"
  >,
) => {
  if (run.finishedAt || !engine) return false;

  let status;
  try {
    status = await engine.status(
      run.workflowId ?? trainingWorkflowId(run.taskId),
      run.id,
    );
  } catch (error) {
    console.warn("Could not reconcile training workflow.", {
      runId: run.id,
      error,
    });
    return false;
  }

  if (status === "running") return false;

  await createTrainingRunStore(database).transition(
    run.id,
    run.stage === "cancelling" ? "cancelled" : status,
  );
  return true;
};
