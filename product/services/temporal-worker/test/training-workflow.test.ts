import proto from "@temporalio/proto";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { randomUUID } from "node:crypto";
import { afterAll, beforeAll, describe, expect, it, vi } from "vitest";
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
    environment = await TestWorkflowEnvironment.createTimeSkipping({
      client: { dataConverter: converter },
    });
    bundle = await bundleWorkflowCode({
      workflowsPath: fileURLToPath(
        new URL("../src/training/workflows.ts", import.meta.url),
      ),
      failureConverterPath: converter.failureConverterPath!,
    });
  }, 60_000);
  afterAll(async () => {
    await environment?.teardown();
  });

  const activities = () =>
    ({
      createRun: vi.fn(async () => {}),
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
