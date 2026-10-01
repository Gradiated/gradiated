import { Context } from "@temporalio/activity";
import { expect, it, vi } from "vitest";
import {
  ControlServiceError,
  TrainingAdmissionError,
  prepareTraining,
  type ControlDatabase,
  type TrainingArtifacts,
  type TrainingEngine,
} from "@gradiated/control";
import { createMemoryContentStore } from "../../../packages/control/test/support/content-store.js";
import { createTrainingExecutorActivities } from "../src/training/executor-activities.js";
import { createMockTrainingActivities } from "../src/training/activities.js";

vi.mock("@gradiated/control", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@gradiated/control")>()),
  prepareTraining: vi.fn(),
}));

it.each([
  new ControlServiceError("not_found", "Task missing or archived"),
  new TrainingAdmissionError("already_training", "Already training"),
  new ControlServiceError("unavailable", "Storage unavailable"),
])(
  "skips ineligible scheduled targets but propagates outages: $code",
  async (failure) => {
    const current = vi.spyOn(Context, "current").mockReturnValue({
      heartbeat: vi.fn(),
      cancellationSignal: new AbortController().signal,
    } as unknown as Context);
    vi.mocked(prepareTraining).mockRejectedValueOnce(failure);
    const activities = createTrainingExecutorActivities({
      database: {} as ControlDatabase,
      engine: {} as TrainingEngine,
      artifacts: {} as TrainingArtifacts,
      contents: createMemoryContentStore(new Map()),
      nomad: vi.fn(),
      podIds: [],
      host: {
        bundleUrl: "test",
        bundleSha256: "a".repeat(64),
        baseId: "test",
        gpuType: "H100",
      },
      token: "test",
    });
    try {
      const result = activities.prepareTrainingRun("task-id");
      if (failure.code === "unavailable")
        await expect(result).rejects.toBe(failure);
      else await expect(result).resolves.toBeNull();
    } finally {
      current.mockRestore();
    }
  },
);

it("makes legacy mock schedules a no-op when scheduled mock runs are disabled", async () => {
  const activities = createMockTrainingActivities(
    {} as ControlDatabase,
    createMemoryContentStore(new Map()),
    false,
  );
  await expect(activities.prepareRun("old-scheduled-task")).resolves.toBeNull();
});
