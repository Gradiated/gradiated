import { TRAINING_RECIPE } from "@gradiated/contracts";
import proto from "@temporalio/proto";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { randomUUID } from "node:crypto";
import {
  afterEach,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";
import { Context } from "@temporalio/activity";
import { TestWorkflowEnvironment } from "@temporalio/testing";
import {
  Worker,
  bundleWorkflowCode,
  type WorkflowBundle,
} from "@temporalio/worker";
import { createDataConverter } from "@gradiated/temporal";
import type { TrainingInput } from "@gradiated/control";
import type { TrainingActivities } from "../src/training/activities.js";

const input: TrainingInput = {
  taskId: randomUUID(),
  workspaceId: randomUUID(),
  name: "private-task",
  baseModelId: "private-base",
  comparisonModelId: "private-comparison",
  judgeModelId: "openai/gpt-5",
  inputCutoff: "2026-09-29T00:00:00Z",
  trigger: "manual",
  requestedBy: null,
};
const adapter = {
  format: "peft_lora" as const,
  artifact_uri: "s3://test/adapter",
  sha256: "a".repeat(64),
  size_bytes: 1,
  rank: 1,
};
const converter = await createDataConverter({
  currentKeyId: "test",
  keys: { test: Buffer.alloc(32, 1).toString("base64") },
});

describe("training workflow", () => {
  let environment: TestWorkflowEnvironment;
  let bundle: WorkflowBundle;
  beforeAll(async () => {
    bundle = await bundleWorkflowCode({
      workflowsPath: fileURLToPath(
        new URL("../src/training/workflows.ts", import.meta.url),
      ),
      failureConverterPath: converter.failureConverterPath!,
    });
  }, 60_000);
  beforeEach(async () => {
    environment = await TestWorkflowEnvironment.createTimeSkipping({
      client: { dataConverter: converter },
    });
  }, 60_000);
  afterEach(async () => {
    await environment?.teardown();
  });

  const activities = () =>
    ({
      createRun: vi.fn(async () => true),
      enterStage: vi.fn(async () => {}),
      finishRun: vi.fn(async () => {}),
      buildDataset: vi.fn(async () => {}),
      allocateHost: vi.fn(async () => ({ id: "host" })),
      train: vi.fn(async () => adapter),
      verify: vi.fn(async () => {}),
      publish: vi.fn(async () => {}),
      evaluate: vi.fn(async () => {}),
      releaseHost: vi.fn(async () => {}),
      prepareRun: vi.fn(
        async (_taskId: string): Promise<TrainingInput | null> => null,
      ),
    }) satisfies TrainingActivities;

  it.each(["train", "verify", "publish", "evaluate"] as const)(
    "retries only %s and replays encrypted history",
    async (step) => {
      const handlers = activities();
      handlers[step].mockRejectedValueOnce(new Error("private failure"));
      const taskQueue = randomUUID();
      const worker = await Worker.create({
        connection: environment.nativeConnection,
        taskQueue,
        workflowBundle: bundle,
        dataConverter: converter,
        activities: handlers,
        maxHeartbeatThrottleInterval: "100 milliseconds",
        defaultHeartbeatThrottleInterval: "100 milliseconds",
      });
      const history = await worker.runUntil(async () => {
        const handle = await environment.client.workflow.start(
          "trainingRunV1",
          { workflowId: `training-${randomUUID()}`, taskQueue, args: [input] },
        );
        await handle.result();
        expect(handlers[step]).toHaveBeenCalledTimes(2);
        expect(handlers.buildDataset).toHaveBeenCalledTimes(1);
        expect(handlers.allocateHost).toHaveBeenCalledTimes(1);
        expect(handlers.releaseHost).toHaveBeenCalledTimes(1);
        expect(handlers.finishRun).toHaveBeenCalledWith(
          handle.firstExecutionRunId,
          "succeeded",
        );

        return handle.fetchHistory();
      });
      const payload = history.events?.find(
        (event) => event.workflowExecutionStartedEventAttributes,
      )?.workflowExecutionStartedEventAttributes?.input?.payloads?.[0];
      expect(Buffer.from(payload?.metadata?.encoding ?? []).toString()).toBe(
        "binary/encrypted",
      );
      expect(JSON.stringify(history)).not.toContain("private-task");
      expect(JSON.stringify(history)).not.toContain("private failure");
      await Worker.runReplayHistory(
        { workflowBundle: bundle, dataConverter: converter },
        history,
      );
      if (process.env.UPDATE_TRAINING_HISTORY === "1" && step === "train") {
        await mkdir(new URL("./fixtures/", import.meta.url), {
          recursive: true,
        });
        await writeFile(
          new URL("./fixtures/training-v1-history.json", import.meta.url),
          JSON.stringify(history, null, 2),
        );
      }
    },
    60_000,
  );

  const executorActivities = () => {
    const artifact = {
      key: "runs/test/adapter",
      sha256: "a".repeat(64),
      size_bytes: 10,
    };
    const handlers = {
      ...activities(),
      prepareTrainingRun: vi.fn(
        async (): Promise<TrainingInput | null> => input,
      ),
      buildTrainingDataset: vi.fn(async () => ({
        train: artifact,
        validation: artifact,
        evaluation: artifact,
        host: {
          bundleUrl: "test",
          bundleSha256: "a".repeat(64),
          baseId: "test",
          gpuType: "H100",
        },
        recipe: TRAINING_RECIPE,
      })),
      allocateTrainingHost: vi.fn(async (_runId: string, ordinal: number) => ({
        allocationId: "allocation-" + ordinal,
        jobId: "job-" + ordinal,
        url: "https://test",
      })),
      trainAdapter: vi.fn(async () => artifact),
      verifyAdapter: vi.fn(async () => undefined),
      publishAdapter: vi.fn(async () => undefined),
      evaluateAdapter: vi.fn(async () => undefined),
      renewTrainingHost: vi.fn(async () => undefined),
      releaseTrainingHost: vi.fn(async () => undefined),
    };
    return handlers;
  };

  it.each([false, true])(
    "checks eligibility before scheduled SFT: %s",
    async (eligible) => {
      const handlers = executorActivities();
      handlers.prepareTrainingRun.mockResolvedValue(eligible ? input : null);
      const taskQueue = randomUUID();
      const worker = await Worker.create({
        connection: environment.nativeConnection,
        taskQueue,
        workflowBundle: bundle,
        dataConverter: converter,
        activities: handlers,
      });
      await worker.runUntil(async () => {
        const handle = await environment.client.workflow.start(
          "trainingRunV2",
          {
            workflowId: randomUUID(),
            taskQueue,
            args: [input.taskId],
          },
        );
        await handle.result();
        const history = await handle.fetchHistory();
        expect(
          history.events?.some(
            (event) =>
              event.startChildWorkflowExecutionInitiatedEventAttributes,
          ),
        ).toBe(false);
        expect(handlers.prepareTrainingRun).toHaveBeenCalledWith(input.taskId);
        expect(handlers.trainAdapter).toHaveBeenCalledTimes(eligible ? 1 : 0);
        expect(handlers.finishRun).toHaveBeenCalledTimes(eligible ? 1 : 0);
      });
    },
    60_000,
  );

  it("skips scheduled training when another run wins admission without creating a child workflow", async () => {
    const handlers = executorActivities();
    handlers.createRun.mockResolvedValue(false);
    const taskQueue = randomUUID();
    const worker = await Worker.create({
      connection: environment.nativeConnection,
      taskQueue,
      workflowBundle: bundle,
      dataConverter: converter,
      activities: handlers,
    });
    await worker.runUntil(async () => {
      const handle = await environment.client.workflow.start("trainingRunV2", {
        workflowId: randomUUID(),
        taskQueue,
        args: [input.taskId],
      });
      await handle.result();
      const history = await handle.fetchHistory();
      expect(
        history.events?.some(
          (event) => event.startChildWorkflowExecutionInitiatedEventAttributes,
        ),
      ).toBe(false);
      expect(handlers.createRun).toHaveBeenCalledWith(
        handle.firstExecutionRunId,
        input,
        handle.workflowId,
      );
      expect(handlers.buildTrainingDataset).not.toHaveBeenCalled();
      expect(handlers.finishRun).not.toHaveBeenCalled();
    });
  }, 60_000);

  it.each(["trainAdapter", "verifyAdapter", "evaluateAdapter"] as const)(
    "replaces a failed SFT host before retrying only %s",
    async (failedStep) => {
      const order: string[] = [];
      const handlers = executorActivities();
      handlers.allocateTrainingHost.mockImplementation(
        async (_runId, ordinal) => {
          if (ordinal > 1)
            expect(
              (await environment.currentTimeMs()) - shutdownAt,
            ).toBeGreaterThanOrEqual(240_000);
          order.push("allocate " + ordinal);
          return {
            allocationId: "allocation-" + ordinal,
            jobId: "job-" + ordinal,
            url: "https://test",
          };
        },
      );
      let shutdownAt = 0;
      handlers.releaseTrainingHost.mockImplementation(async () => {
        shutdownAt = await environment.currentTimeMs();
        order.push("shutdown requested");
        throw new Error("Nomad unreachable");
      });
      handlers[failedStep].mockRejectedValueOnce(new Error("host failed"));
      const taskQueue = randomUUID();
      const worker = await Worker.create({
        connection: environment.nativeConnection,
        taskQueue,
        workflowBundle: bundle,
        dataConverter: converter,
        activities: handlers,
      });
      await worker.runUntil(async () => {
        await environment.client.workflow.execute("trainingRunV2", {
          workflowId: randomUUID(),
          taskQueue,
          args: [input],
        });
        expect(order).toEqual([
          "allocate 1",
          "shutdown requested",
          "allocate 2",
          "shutdown requested",
        ]);
        expect(handlers[failedStep]).toHaveBeenCalledTimes(2);
        expect(handlers.buildTrainingDataset).toHaveBeenCalledTimes(1);
        expect(handlers.publishAdapter).toHaveBeenCalledTimes(1);
        if (failedStep !== "trainAdapter")
          expect(handlers.trainAdapter).toHaveBeenCalledTimes(1);
      });
    },
    60_000,
  );

  it.each(["complete", "cancel", "terminate", "timeout"] as const)(
    "renews during publishing and stops after workflow %s",
    async (ending) => {
      const handlers = executorActivities();
      let publishing!: () => void;
      const entered = new Promise<void>((resolve) => {
        publishing = resolve;
      });
      let release!: () => void;
      const published = new Promise<void>((resolve) => {
        release = resolve;
      });
      let context!: Context;
      handlers.publishAdapter.mockImplementation(async () => {
        context = Context.current();
        publishing();
        const heartbeat = setInterval(() => context.heartbeat(), 1000);
        try {
          await Promise.race([published, context.cancelled]);
        } finally {
          clearInterval(heartbeat);
        }
      });
      const taskQueue = randomUUID();
      const worker = await Worker.create({
        connection: environment.nativeConnection,
        taskQueue,
        workflowBundle: bundle,
        dataConverter: converter,
        activities: handlers,
        maxHeartbeatThrottleInterval: "1 ms",
        defaultHeartbeatThrottleInterval: "1 ms",
      });
      await worker.runUntil(async () => {
        const handle = await environment.client.workflow.start(
          "trainingRunV2",
          {
            workflowId: randomUUID(),
            taskQueue,
            args: [input],
            workflowExecutionTimeout:
              ending === "timeout" ? "40 seconds" : "24 hours",
          },
        );
        try {
          await entered;
          const before = handlers.renewTrainingHost.mock.calls.length;
          for (let step = 0; step < 3; step++) {
            context.heartbeat();
            await environment.sleep("11 seconds");
          }
          expect(handlers.renewTrainingHost.mock.calls.length).toBeGreaterThan(
            before,
          );
          expect(handlers.publishAdapter).toHaveBeenCalledTimes(1);
          if (ending === "complete") {
            release();
            await handle.result();
            expect(handlers.releaseTrainingHost).toHaveBeenCalledTimes(1);
          } else {
            if (ending === "terminate") await handle.terminate();
            else if (ending === "cancel") {
              await handle.cancel();
            } else await environment.sleep("10 seconds");
            await expect(handle.result()).rejects.toThrow();
            if (ending === "cancel") {
              expect(handlers.releaseTrainingHost).toHaveBeenCalledTimes(1);
              expect(handlers.finishRun).toHaveBeenCalledWith(
                expect.any(String),
                "cancelled",
              );
            }
          }
          release();
          const renewals = handlers.renewTrainingHost.mock.calls.length;
          await new Promise((resolve) => setTimeout(resolve, 200));
          expect(handlers.renewTrainingHost).toHaveBeenCalledTimes(renewals);
        } finally {
          release();
        }
      });
    },
    120_000,
  );

  it("replaces a reservation lost between compute steps without repeating training", async () => {
    const handlers = executorActivities();
    let trained = false;
    handlers.trainAdapter.mockImplementation(async () => {
      trained = true;
      return {
        key: "runs/test/adapter",
        sha256: "a".repeat(64),
        size_bytes: 10,
      };
    });
    handlers.renewTrainingHost.mockImplementation(
      async (...args: unknown[]) => {
        const host = args[0] as { allocationId: string };
        if (trained && host.allocationId === "allocation-1")
          throw new Error("reservation expired");
      },
    );
    const taskQueue = randomUUID();
    const worker = await Worker.create({
      connection: environment.nativeConnection,
      taskQueue,
      workflowBundle: bundle,
      dataConverter: converter,
      activities: handlers,
    });
    await worker.runUntil(async () => {
      await environment.client.workflow.execute("trainingRunV2", {
        workflowId: randomUUID(),
        taskQueue,
        args: [input],
      });
      expect(
        handlers.allocateTrainingHost.mock.calls.map(([, attempt]) => attempt),
      ).toEqual([1, 2]);
      expect(handlers.releaseTrainingHost).toHaveBeenCalledTimes(2);
      expect(handlers.trainAdapter).toHaveBeenCalledTimes(1);
      expect(handlers.verifyAdapter).toHaveBeenCalledTimes(1);
    });
  }, 60_000);

  it.each(["buildTrainingDataset", "trainAdapter"] as const)(
    "records failure and cleans up when %s exhausts its attempts",
    async (step) => {
      const handlers = executorActivities();
      handlers[step].mockRejectedValue(new Error("permanent failure"));
      const taskQueue = randomUUID();
      const worker = await Worker.create({
        connection: environment.nativeConnection,
        taskQueue,
        workflowBundle: bundle,
        dataConverter: converter,
        activities: handlers,
      });

      await worker.runUntil(async () => {
        const handle = await environment.client.workflow.start(
          "trainingRunV2",
          {
            workflowId: randomUUID(),
            taskQueue,
            args: [input],
          },
        );
        await expect(handle.result()).rejects.toThrow();
        expect(handlers[step]).toHaveBeenCalledTimes(3);
        expect(
          handlers.allocateTrainingHost.mock.calls.map(
            ([, ordinal]) => ordinal,
          ),
        ).toEqual(step === "trainAdapter" ? [1, 2, 3] : []);
        expect(handlers.releaseTrainingHost).toHaveBeenCalledTimes(
          step === "trainAdapter" ? 3 : 1,
        );
        expect(handlers.verifyAdapter).not.toHaveBeenCalled();
        expect(handlers.finishRun).toHaveBeenCalledExactlyOnceWith(
          handle.firstExecutionRunId,
          "failed",
        );
      });
    },
    60_000,
  );

  it("records cancellation received during host cleanup instead of success", async () => {
    const handlers = executorActivities();
    let enteredCleanup!: () => void;
    const entered = new Promise<void>((resolve) => {
      enteredCleanup = resolve;
    });
    let releaseCleanup!: () => void;
    const released = new Promise<void>((resolve) => {
      releaseCleanup = resolve;
    });
    handlers.releaseTrainingHost.mockImplementation(async () => {
      enteredCleanup();
      await released;
    });
    const taskQueue = randomUUID();
    const worker = await Worker.create({
      connection: environment.nativeConnection,
      taskQueue,
      workflowBundle: bundle,
      dataConverter: converter,
      activities: handlers,
    });

    await worker.runUntil(async () => {
      const handle = await environment.client.workflow.start("trainingRunV2", {
        workflowId: randomUUID(),
        taskQueue,
        args: [input],
      });
      try {
        await entered;
        await handle.cancel();
        releaseCleanup();
        await expect(handle.result()).rejects.toThrow();
        expect(handlers.releaseTrainingHost).toHaveBeenCalledTimes(1);
        expect(handlers.enterStage).toHaveBeenCalledWith(
          handle.firstExecutionRunId,
          "cancelling",
        );
        expect(handlers.finishRun).toHaveBeenCalledExactlyOnceWith(
          handle.firstExecutionRunId,
          "cancelled",
        );
      } finally {
        releaseCleanup();
      }
    });
  }, 60_000);

  it("fails after three training attempts and releases the host", async () => {
    const handlers = activities();
    handlers.train.mockRejectedValue(new Error("Training failed"));
    const taskQueue = randomUUID();
    const worker = await Worker.create({
      connection: environment.nativeConnection,
      taskQueue,
      workflowBundle: bundle,
      dataConverter: converter,
      activities: handlers,
    });

    await worker.runUntil(async () => {
      const handle = await environment.client.workflow.start("trainingRunV1", {
        workflowId: `training-${randomUUID()}`,
        taskQueue,
        args: [input],
      });
      await expect(handle.result()).rejects.toThrow();
      expect(handlers.train).toHaveBeenCalledTimes(3);
      expect(handlers.buildDataset).toHaveBeenCalledTimes(1);
      expect(handlers.allocateHost).toHaveBeenCalledTimes(1);
      expect(handlers.verify).not.toHaveBeenCalled();
      expect(handlers.releaseHost).toHaveBeenCalledTimes(1);
      expect(handlers.finishRun).toHaveBeenCalledWith(
        handle.firstExecutionRunId,
        "failed",
      );
    });
  }, 60_000);

  it.each([false, true])(
    "checks task eligibility before scheduled training: %s",
    async (eligible) => {
      const handlers = activities();
      handlers.prepareRun.mockResolvedValue(eligible ? input : null);
      const taskQueue = randomUUID();
      const worker = await Worker.create({
        connection: environment.nativeConnection,
        taskQueue,
        workflowBundle: bundle,
        dataConverter: converter,
        activities: handlers,
      });
      await worker.runUntil(async () => {
        await environment.client.workflow.execute("trainingTaskV1", {
          workflowId: `scheduled-${randomUUID()}`,
          taskQueue,
          args: [input.taskId],
        });
        expect(handlers.prepareRun).toHaveBeenCalledWith(input.taskId);
        expect(handlers.createRun).toHaveBeenCalledTimes(eligible ? 1 : 0);
      });
    },
    60000,
  );

  it("skips a scheduled start when a manual execution already owns the task", async () => {
    const handlers = activities();
    handlers.prepareRun.mockResolvedValue(input);
    let release = false;
    handlers.train.mockImplementation(async () => {
      while (!release) {
        Context.current().heartbeat();
        await Context.current().sleep(100);
      }
      return adapter;
    });
    const taskQueue = randomUUID();
    const worker = await Worker.create({
      connection: environment.nativeConnection,
      taskQueue,
      workflowBundle: bundle,
      dataConverter: converter,
      activities: handlers,
    });
    await worker.runUntil(async () => {
      const manual = await environment.client.workflow.start("trainingRunV1", {
        workflowId: `training-${input.taskId}`,
        taskQueue,
        args: [input],
      });
      try {
        await vi.waitFor(() => expect(handlers.train).toHaveBeenCalled(), {
          timeout: 10000,
        });
        await environment.client.workflow.execute("trainingTaskV1", {
          workflowId: `scheduled-${randomUUID()}`,
          taskQueue,
          args: [input.taskId],
        });
        expect(handlers.createRun).toHaveBeenCalledTimes(1);
      } finally {
        release = true;
        await manual.result();
      }
    });
  }, 60000);

  it("replays the frozen v1 history across deployments", async () => {
    const history = proto.temporal.api.history.v1.History.fromObject(
      JSON.parse(
        await readFile(
          new URL("./fixtures/training-v1-history.json", import.meta.url),
          "utf8",
        ),
      ),
    );
    await Worker.runReplayHistory(
      { workflowBundle: bundle, dataConverter: converter },
      history,
    );
  });

  it.each(["train", "releaseHost"] as const)(
    "cancels during %s and releases the host before closing the run",
    async (cancelAt) => {
      const handlers = activities();
      const order: string[] = [];
      let cancelled = false;
      handlers.train.mockImplementation(async () => {
        Context.current().heartbeat();
        try {
          while (cancelAt === "train") {
            Context.current().heartbeat();
            await Context.current().sleep(100);
          }
        } finally {
          order.push("training stopped");
        }
        return adapter;
      });
      handlers.releaseHost.mockImplementation(async () => {
        while (cancelAt === "releaseHost" && !cancelled) {
          Context.current().heartbeat();
          await Context.current().sleep(100);
        }
        order.push("host released");
      });
      handlers.finishRun.mockImplementation(async () => {
        order.push("run closed");
      });
      const taskQueue = randomUUID();
      const worker = await Worker.create({
        connection: environment.nativeConnection,
        taskQueue,
        workflowBundle: bundle,
        dataConverter: converter,
        activities: handlers,
        maxHeartbeatThrottleInterval: "100 milliseconds",
        defaultHeartbeatThrottleInterval: "100 milliseconds",
      });
      await worker.runUntil(async () => {
        const handle = await environment.client.workflow.start(
          "trainingRunV1",
          {
            workflowId: `training-${randomUUID()}`,
            taskQueue,
            args: [input],
          },
        );
        await vi.waitFor(() => expect(handlers[cancelAt]).toHaveBeenCalled(), {
          timeout: 10_000,
        });
        await handle.cancel();
        cancelled = true;
        await expect(handle.result()).rejects.toThrow();
        expect(order).toEqual([
          "training stopped",
          "host released",
          "run closed",
        ]);
        expect(handlers.enterStage).toHaveBeenCalledWith(
          handle.firstExecutionRunId,
          "cancelling",
        );
        expect(handlers.finishRun).toHaveBeenCalledWith(
          handle.firstExecutionRunId,
          "cancelled",
        );
      });
    },
    60_000,
  );
});
