import { rm, writeFile } from "node:fs/promises";

import { serviceLog } from "./logging.js";
import type { WorkerLoop, WorkerMetrics } from "./metrics.js";
import { sleep } from "./sleep.js";

export type LoopHealth = Pick<
  WorkerMetrics,
  "loopStarted" | "loopReadyNow" | "loopFailed" | "loopStopped"
>;

export type SupervisedLoop = {
  loop: WorkerLoop;
  readinessPath: string;
  metrics: LoopHealth;
  signal: AbortSignal;
  run: (markReady: () => Promise<void>) => Promise<void>;
};

const initialRetryMilliseconds = 1_000;
const maxRetryMilliseconds = 30_000;
const healthyRunMilliseconds = 60_000;

export const supervise = async ({
  loop,
  readinessPath,
  metrics,
  signal,
  run,
}: SupervisedLoop): Promise<void> => {
  const markReady = async () => {
    await writeFile(readinessPath, "ready\n", "utf8");
    metrics.loopReadyNow(loop);
  };

  let retryMilliseconds = initialRetryMilliseconds;
  let attempt = 0;

  while (!signal.aborted) {
    attempt += 1;
    serviceLog("info", "worker_loop_started", { loop, attempt });
    metrics.loopStarted(loop, attempt > 1);

    const startedAt = Date.now();

    try {
      await run(markReady);
    } catch (error) {
      if (Date.now() - startedAt >= healthyRunMilliseconds) {
        retryMilliseconds = initialRetryMilliseconds;
      }

      serviceLog("error", "worker_loop_failed", {
        loop,
        attempt,
        retry_ms: retryMilliseconds,
        error,
      });
      metrics.loopFailed(loop);
      await rm(readinessPath, { force: true });
      await sleep(retryMilliseconds, signal);
      retryMilliseconds = Math.min(retryMilliseconds * 2, maxRetryMilliseconds);
    }
  }

  await rm(readinessPath, { force: true });
  metrics.loopStopped(loop);
  serviceLog("info", "worker_loop_stopped", { loop });
};
