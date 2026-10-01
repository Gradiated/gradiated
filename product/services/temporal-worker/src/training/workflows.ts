import { WorkflowExecutionAlreadyStartedError } from "@temporalio/common";
import {
  CancellationScope,
  CancelledFailure,
  isCancellation,
  proxyActivities,
  workflowInfo,
  startChild,
  ParentClosePolicy,
} from "@temporalio/workflow";
import type { TrainingInput } from "@gradiated/control";
import type { TrainingActivities } from "./activities.js";

const activities = proxyActivities<TrainingActivities>({
  startToCloseTimeout: "10 minutes",
  scheduleToCloseTimeout: "24 hours",
  heartbeatTimeout: "30 seconds",
  cancellationType: "WAIT_CANCELLATION_COMPLETED",
  retry: {
    initialInterval: "1 second",
    maximumInterval: "1 minute",
    maximumAttempts: 3,
  },
});
const records = proxyActivities<
  Pick<TrainingActivities, "createRun" | "enterStage" | "finishRun">
>({
  startToCloseTimeout: "30 seconds",
  retry: { initialInterval: "1 second", maximumInterval: "1 minute" },
});
const cleanup = proxyActivities<Pick<TrainingActivities, "releaseHost">>({
  startToCloseTimeout: "5 minutes",
  heartbeatTimeout: "30 seconds",
  retry: { initialInterval: "1 second", maximumInterval: "1 minute" },
});

export const trainingRunV1 = async (input: TrainingInput): Promise<void> => {
  const runId = workflowInfo().runId;
  const scope = CancellationScope.current();
  let failure: unknown;
  let outcome: "succeeded" | "failed" | "cancelled" = "succeeded";

  await CancellationScope.nonCancellable(() => records.createRun(runId, input));
  try {
    await records.enterStage(runId, "building_dataset");
    await activities.buildDataset(runId, input);
    await records.enterStage(runId, "awaiting_capacity");
    const host = await activities.allocateHost(runId, input);
    await records.enterStage(runId, "training");
    const adapter = await activities.train(runId, input, host);
    await records.enterStage(runId, "verifying");
    await activities.verify(runId, adapter, host);
    await records.enterStage(runId, "publishing");
    await activities.publish(runId, input, adapter);
    await records.enterStage(runId, "evaluating");
    await activities.evaluate(runId, input, host);
  } catch (error) {
    failure = error;
    outcome = isCancellation(error) ? "cancelled" : "failed";
  } finally {
    await CancellationScope.nonCancellable(async () => {
      if (outcome === "cancelled")
        await records.enterStage(runId, "cancelling");
      await cleanup.releaseHost(runId);
      if (outcome !== "cancelled" && scope.consideredCancelled) {
        outcome = "cancelled";
        failure = new CancelledFailure("Training cancelled");
        await records.enterStage(runId, "cancelling");
      }
      await records.finishRun(runId, outcome);
    });
  }
  if (failure) throw failure;
};

export const trainingTaskV1 = async (taskId: string): Promise<void> => {
  const input = await activities.prepareRun(taskId);
  if (!input) return;

  let child;
  try {
    child = await startChild(trainingRunV1, {
      workflowId: `training-${taskId}`,
      args: [input],
      parentClosePolicy: ParentClosePolicy.ABANDON,
    });
  } catch (error) {
    if (error instanceof WorkflowExecutionAlreadyStartedError) return;
    throw error;
  }
  await child.result();
};

export { trainingRunV2 } from "./run-workflow.js";
