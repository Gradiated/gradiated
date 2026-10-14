import { randomUUID } from "node:crypto";
import { expect, it, vi } from "vitest";
import { stopClosedTrainingJobs } from "../src/training/cleanup.js";
const runId = randomUUID(),
  taskId = randomUUID(),
  uid = randomUUID();
const job = {
  metadata: {
    name: `training-${runId}-1`,
    uid,
    labels: { "gradiated.com/training-run": runId },
  },
  status: { conditions: [] },
};
const setup = () => ({
  request: vi.fn(async (_path: string, method?: string): Promise<unknown> =>
    method === "DELETE" ? {} : { items: [job] },
  ),
  engine: {
    status: vi.fn(async (): Promise<"running" | "failed"> => "failed"),
  },
  readRun: vi.fn(
    async (): Promise<
      { taskId: string; workflowId: string | null } | undefined
    > => ({ taskId, workflowId: "exact-workflow" }),
  ),
});
it("deletes only the closed workflow Job with a UID precondition", async () => {
  const input = setup();
  await stopClosedTrainingJobs(input);
  expect(input.engine.status).toHaveBeenCalledWith("exact-workflow", runId);
  expect(input.request).toHaveBeenLastCalledWith(
    `/apis/batch/v1/namespaces/gpu-inference/jobs/${job.metadata.name}`,
    "DELETE",
    expect.objectContaining({
      preconditions: { uid },
      propagationPolicy: "Foreground",
    }),
  );
});
it("uses the task workflow identity for older run records", async () => {
  const input = setup();
  input.readRun.mockResolvedValueOnce({ taskId, workflowId: null });
  await stopClosedTrainingJobs(input);
  expect(input.engine.status).toHaveBeenCalledWith(`training-${taskId}`, runId);
});
it.each(["running", "missing-run", "database-down", "temporal-down"])(
  "preserves capacity when ownership is %s",
  async (condition) => {
    const input = setup();
    if (condition === "running")
      input.engine.status.mockResolvedValueOnce("running");
    if (condition === "missing-run")
      input.readRun.mockResolvedValueOnce(undefined);
    if (condition === "database-down")
      input.readRun.mockRejectedValueOnce(new Error("unavailable"));
    if (condition === "temporal-down")
      input.engine.status.mockRejectedValueOnce(new Error("unavailable"));
    await stopClosedTrainingJobs(input);
    expect(input.request).toHaveBeenCalledTimes(1);
  },
);
it("ignores completed, deleting, malformed and mismatched jobs", async () => {
  const input = setup();
  input.request.mockResolvedValueOnce({
    items: [
      {
        ...job,
        status: { conditions: [{ type: "Complete", status: "True" }] },
      },
      { ...job, metadata: { ...job.metadata, deletionTimestamp: "today" } },
      { ...job, metadata: { ...job.metadata, name: "training-bad-1" } },
      {
        ...job,
        metadata: {
          ...job.metadata,
          labels: { "gradiated.com/training-run": randomUUID() },
        },
      },
    ],
  });
  await stopClosedTrainingJobs(input);
  expect(input.readRun).not.toHaveBeenCalled();
});
it("continues through paginated Jobs", async () => {
  const input = setup();
  input.request.mockResolvedValueOnce({
    items: [],
    metadata: { continue: "next" },
  });
  await stopClosedTrainingJobs(input);
  expect(input.request).toHaveBeenNthCalledWith(
    2,
    expect.stringContaining("&continue=next"),
  );
  expect(input.readRun).toHaveBeenCalledWith(runId);
});
