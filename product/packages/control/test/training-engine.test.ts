import { expect, it, vi } from "vitest";
import type { Client } from "@gradiated/temporal";
import { WorkflowNotFoundError } from "@gradiated/temporal";
import { createTemporalTrainingEngine } from "../src/training/engine.js";

const fixture = () => {
  const describe = vi.fn();
  const getHandle = vi.fn(() => ({ describe }));
  const client = { workflow: { getHandle } } as unknown as Client;
  return { describe, getHandle, engine: createTemporalTrainingEngine(client) };
};

it.each([
  ["RUNNING", "running"],
  ["CONTINUED_AS_NEW", "running"],
  ["COMPLETED", "succeeded"],
  ["CANCELLED", "cancelled"],
  ["FAILED", "failed"],
  ["TERMINATED", "failed"],
  ["TIMED_OUT", "failed"],
])(
  "maps Temporal %s to %s for the exact stored execution",
  async (name, expected) => {
    const f = fixture();
    f.describe.mockResolvedValue({ status: { name } });
    expect(await f.engine.status("generated-schedule-id", "exact-run-id")).toBe(
      expected,
    );
    expect(f.getHandle).toHaveBeenCalledExactlyOnceWith(
      "generated-schedule-id",
      "exact-run-id",
    );
  },
);

it("treats a missing execution as failed after Temporal has discarded its history", async () => {
  const f = fixture();
  f.describe.mockRejectedValue(
    new WorkflowNotFoundError("gone", "workflow", "run"),
  );
  expect(await f.engine.status("workflow", "run")).toBe("failed");
});

it("propagates a status lookup failure without inventing a terminal outcome", async () => {
  const f = fixture();
  const failure = new Error("Temporal unavailable");
  f.describe.mockRejectedValue(failure);
  await expect(f.engine.status("workflow", "run")).rejects.toBe(failure);
});
