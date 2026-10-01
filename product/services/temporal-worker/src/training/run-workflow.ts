import {
  CancellationScope,
  CancelledFailure,
  isCancellation,
  proxyActivities,
  workflowInfo,
  sleep,
  log,
} from "@temporalio/workflow";
import type { TrainingInput } from "@gradiated/control";
import type { TrainingActivities } from "./activities.js";
import type { TrainingExecutorActivities } from "./executor-activities.js";
import type { TrainingHost, TrainingHostConfig } from "./nomad-host.js";

const records = proxyActivities<
  Pick<TrainingActivities, "createRun" | "enterStage" | "finishRun">
>({
  startToCloseTimeout: "30 seconds",
  retry: { initialInterval: "1 second", maximumInterval: "1 minute" },
});
const data = proxyActivities<
  Pick<TrainingExecutorActivities, "buildTrainingDataset" | "publishAdapter">
>({
  startToCloseTimeout: "30 minutes",
  heartbeatTimeout: "30 seconds",
  cancellationType: "WAIT_CANCELLATION_COMPLETED",
  scheduleToCloseTimeout: "24 hours",
  retry: {
    initialInterval: "1 second",
    maximumInterval: "1 minute",
    maximumAttempts: 3,
  },
});
const gpu = proxyActivities<
  Pick<
    TrainingExecutorActivities,
    | "allocateTrainingHost"
    | "trainAdapter"
    | "verifyAdapter"
    | "evaluateAdapter"
  >
>({
  startToCloseTimeout: "2 hours",
  heartbeatTimeout: "30 seconds",
  cancellationType: "WAIT_CANCELLATION_COMPLETED",
  retry: { maximumAttempts: 1 },
});
const leases = proxyActivities<
  Pick<TrainingExecutorActivities, "renewTrainingHost">
>({
  startToCloseTimeout: "30 seconds",
  scheduleToCloseTimeout: "1 minute",
  retry: {
    initialInterval: "1 second",
    maximumInterval: "5 seconds",
    maximumAttempts: 3,
  },
});
const cleanup = proxyActivities<
  Pick<TrainingExecutorActivities, "releaseTrainingHost">
>({
  startToCloseTimeout: "30 seconds",
  scheduleToCloseTimeout: "45 seconds",
  retry: { maximumAttempts: 1 },
});

const admission = proxyActivities<
  Pick<TrainingExecutorActivities, "prepareTrainingRun">
>({
  startToCloseTimeout: "10 minutes",
  scheduleToCloseTimeout: "24 hours",
  heartbeatTimeout: "30 seconds",
  cancellationType: "WAIT_CANCELLATION_COMPLETED",
  retry: {
    maximumAttempts: 3,
    initialInterval: "1 second",
    maximumInterval: "1 minute",
  },
});

const requestHostShutdown = async (runId: string) => {
  try {
    await cleanup.releaseTrainingHost(runId);
  } catch (error) {
    log.warn("Training shutdown request failed; reservation will expire.", {
      error,
    });
  }
};

const createHostReservation = (
  runId: string,
  configuration: TrainingHostConfig,
) => {
  let reservation: { host: TrainingHost; lost: boolean } | undefined;
  let ordinal = 1;

  const renewalScope = new CancellationScope();
  const renewalTask = renewalScope
    .run(async () => {
      for (;;) {
        await sleep("30 seconds");
        if (!reservation || reservation.lost) continue;

        const current = reservation;
        try {
          await leases.renewTrainingHost(current.host);
        } catch (error) {
          if (isCancellation(error)) throw error;
          current.lost = true;
        }
      }
    })
    .catch((error: unknown) => {
      if (!isCancellation(error)) throw error;
    });

  const acquire = async () => {
    const deadline = Date.now() + 12 * 60 * 60 * 1000;

    if (reservation?.lost) throw new Error("Training reservation was lost.");

    while (!reservation) {
      const host = await gpu.allocateTrainingHost(
        runId,
        ordinal,
        configuration,
      );
      if (host) reservation = { host, lost: false };
      else {
        if (Date.now() >= deadline)
          throw new Error("Training capacity deadline exceeded.");
        await sleep("30 seconds");
      }
    }

    await leases.renewTrainingHost(reservation.host);
    return reservation.host;
  };

  const run = async <T>(
    step: (host: TrainingHost, ordinal: number) => Promise<T>,
  ): Promise<T> => {
    for (let attempt = 1; ; attempt++) {
      try {
        const host = await acquire();
        return await step(host, ordinal);
      } catch (error) {
        if (isCancellation(error) || attempt === 3) throw error;

        const hadHost = Boolean(reservation);
        reservation = undefined;
        await CancellationScope.nonCancellable(() =>
          requestHostShutdown(runId),
        );
        // Cover a pending renewal, the three-minute lease and ten-second exit grace.
        if (hadHost) await sleep("4 minutes");
        ordinal++;
      }
    }
  };

  return {
    run,
    stopRenewing: async () => {
      renewalScope.cancel();
      await renewalTask;
    },
  };
};

export const trainingRunV2 = async (request: TrainingInput | string) => {
  const { runId, workflowId } = workflowInfo();
  const input =
    typeof request === "string"
      ? await admission.prepareTrainingRun(request)
      : request;
  if (!input) return;

  const created = await CancellationScope.nonCancellable(() =>
    records.createRun(runId, input, workflowId),
  );
  if (!created) return;

  const scope = CancellationScope.current();
  let reservation: ReturnType<typeof createHostReservation> | undefined;
  let outcome: "succeeded" | "failed" | "cancelled" = "succeeded";
  let failure: unknown;

  try {
    await records.enterStage(runId, "building_dataset");
    const dataset = await data.buildTrainingDataset(runId, input);
    reservation = createHostReservation(runId, dataset.host);

    await records.enterStage(runId, "awaiting_capacity");
    await reservation.run(async () => undefined);

    await records.enterStage(runId, "training");
    const adapter = await reservation.run((current, attempt) =>
      gpu.trainAdapter(runId, attempt, current, dataset),
    );

    await records.enterStage(runId, "verifying");
    await reservation.run((current, attempt) =>
      gpu.verifyAdapter(runId, attempt, current, adapter),
    );

    await records.enterStage(runId, "publishing");
    await data.publishAdapter(runId, input, adapter, dataset.recipe.rank);

    await records.enterStage(runId, "evaluating");
    await reservation.run((current, attempt) =>
      gpu.evaluateAdapter(runId, attempt, current, input, dataset, adapter),
    );
  } catch (error) {
    failure = error;
    outcome = isCancellation(error) ? "cancelled" : "failed";
  } finally {
    await CancellationScope.nonCancellable(async () => {
      await reservation?.stopRenewing();
      if (outcome === "cancelled")
        await records.enterStage(runId, "cancelling");

      await requestHostShutdown(runId);

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
