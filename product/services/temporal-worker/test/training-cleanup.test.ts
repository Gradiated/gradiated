import { randomUUID } from "node:crypto";
import { expect, it, vi } from "vitest";
import { stopClosedTrainingJobs } from "../src/training/cleanup.js";

const runId = randomUUID();
const taskId = randomUUID();
const jobId = `training-${runId}-1`;

const setup = () => {
  const request = vi.fn(
    async (path: string, method?: string): Promise<unknown> =>
      method === "DELETE"
        ? {}
        : [{ ID: jobId, Stop: false, Status: "pending" }],
  );
  const status = vi.fn(async (): Promise<"running" | "failed"> => "failed");
  const readRun = vi.fn(
    async (): Promise<
      { taskId: string; workflowId: string | null } | undefined
    > => ({
      taskId,
      workflowId: "exact-workflow",
    }),
  );
  return { request, engine: { status }, readRun };
};

it.each(["pending", "running"])(
  "stops a %s job only after its exact workflow execution closes",
  async (state) => {
    const input = setup();
    input.request.mockResolvedValueOnce([
      { ID: jobId, Stop: false, Status: state },
    ]);

    await stopClosedTrainingJobs(input);

    expect(input.engine.status).toHaveBeenCalledWith("exact-workflow", runId);
    expect(input.request).toHaveBeenLastCalledWith(
      `/v1/job/${jobId}?purge=false`,
      "DELETE",
    );
  },
);

it("uses the task workflow identity for older run records", async () => {
  const input = setup();
  input.readRun.mockResolvedValueOnce({ taskId, workflowId: null });

  await stopClosedTrainingJobs(input);

  expect(input.engine.status).toHaveBeenCalledWith(`training-${taskId}`, runId);
});

it.each(["running", "missing-run", "database-down", "temporal-down"])(
  "leaves capacity alone when ownership is %s",
  async (condition) => {
    const input = setup();
    if (condition === "running")
      input.engine.status.mockResolvedValueOnce("running");
    if (condition === "missing-run")
      input.readRun.mockResolvedValueOnce(undefined);
    if (condition === "database-down")
      input.readRun.mockRejectedValueOnce(new Error("Unavailable"));
    if (condition === "temporal-down")
      input.engine.status.mockRejectedValueOnce(new Error("Unavailable"));

    await stopClosedTrainingJobs(input);

    expect(input.request).toHaveBeenCalledTimes(1);
  },
);

it("ignores stopped, dead, malformed and unrelated jobs", async () => {
  const input = setup();
  input.request.mockResolvedValueOnce([
    { ID: jobId, Stop: true, Status: "pending" },
    { ID: jobId, Stop: false, Status: "dead" },
    { ID: "training-not-a-run-1", Stop: false, Status: "running" },
    { ID: `inference-${runId}-1`, Stop: false, Status: "running" },
  ]);

  await stopClosedTrainingJobs(input);

  expect(input.readRun).not.toHaveBeenCalled();
  expect(input.request).toHaveBeenCalledTimes(1);
});

it("continues after one job cannot be stopped", async () => {
  const input = setup();
  input.request
    .mockResolvedValueOnce([
      { ID: jobId, Stop: false, Status: "pending" },
      { ID: `training-${runId}-2`, Stop: false, Status: "running" },
    ])
    .mockRejectedValueOnce(new Error("Nomad unavailable"));

  await stopClosedTrainingJobs(input);

  expect(input.request).toHaveBeenLastCalledWith(
    `/v1/job/training-${runId}-2?purge=false`,
    "DELETE",
  );
});
