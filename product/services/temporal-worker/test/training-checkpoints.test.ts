import { Context } from "@temporalio/activity";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type {
  ControlDatabase,
  TrainingArtifacts,
  TrainingEngine,
} from "@gradiated/control";
import { createMemoryContentStore } from "../../../packages/control/test/support/content-store.js";
import { createTrainingExecutorActivities } from "../src/training/executor-activities.js";
import type { TrainingHost } from "../src/training/kubernetes-host.js";

const { call } = vi.hoisted(() => ({ call: vi.fn() }));
vi.mock("../src/training/kubernetes-host.js", () => ({
  createTrainingHosts: () => ({ call }),
}));
vi.mock("@gradiated/control", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@gradiated/control")>()),
  createTrainingRunStore: () => ({ appendTrainerEvents: vi.fn() }),
}));

const runId = "01900000-0000-7000-8000-000000000001";
const artifact = (key: string) => ({
  key: `runs/${runId}/${key}`,
  sha256: "a".repeat(64),
  size_bytes: 10,
});
const dataset = {
  train: artifact("dataset/v1/train.jsonl"),
  validation: artifact("dataset/v1/validation.jsonl"),
  evaluation: artifact("dataset/v1/evaluation.jsonl"),
  host: {
    bundleUrl: "test",
    bundleSha256: "b",
    baseId: "test",
    gpuType: "H100",
  },
  recipe: {
    id: "sft",
    model: "test",
    revision: "main",
    max_steps: 10,
    checkpoint_steps: 10,
    rank: 16,
  },
};

const activities = (artifacts: TrainingArtifacts) =>
  createTrainingExecutorActivities({
    database: {} as ControlDatabase,
    engine: {} as TrainingEngine,
    artifacts,
    contents: createMemoryContentStore(new Map()),
    request: vi.fn(),
    podIds: [],
    host: dataset.host,
  });

const fakeArtifacts = () =>
  ({
    exists: vi.fn(async () => false),
    upload: vi.fn(async (key: string) => ({ key, url: "https://upload" })),
    download: vi.fn(async (value: object) => ({
      ...value,
      url: "https://get",
    })),
    verify: vi.fn(async () => {}),
    markExpiring: vi.fn(async () => {}),
    put: vi.fn(async (key: string, bytes: Uint8Array) => ({
      key,
      sha256: "c".repeat(64),
      size_bytes: bytes.length,
    })),
  }) as unknown as TrainingArtifacts & {
    [K in "verify" | "markExpiring" | "put"]: ReturnType<typeof vi.fn>;
  };

const trainerReports = (checkpointKey: string) =>
  call.mockImplementation(async (_host: TrainingHost, path: string) =>
    path === "/operations"
      ? {}
      : {
          status: "complete",
          events: [
            {
              type: "trainer_checkpoint",
              step: 10,
              ...artifact(checkpointKey),
            },
          ],
          next: 1,
          total: 1,
          result: artifact("output/0/adapter.tar.gz"),
        },
  );

beforeEach(() => {
  vi.spyOn(Context, "current").mockReturnValue({
    heartbeat: vi.fn(),
    sleep: vi.fn(),
    cancellationSignal: new AbortController().signal,
    info: { attempt: 1 },
  } as unknown as Context);
});
afterEach(() => vi.restoreAllMocks());

it("tags each verified checkpoint and latest.json for 90-day expiry, but not the adapter", async () => {
  const artifacts = fakeArtifacts();
  trainerReports("checkpoints/0/10.tar.gz");

  await activities(artifacts).trainAdapter(
    runId,
    0,
    { url: "http://trainer" } as TrainingHost,
    dataset,
  );

  const checkpoint = artifact("checkpoints/0/10.tar.gz");
  expect(artifacts.verify).toHaveBeenCalledWith(checkpoint);
  expect(artifacts.markExpiring).toHaveBeenCalledExactlyOnceWith(
    checkpoint.key,
  );
  expect(artifacts.verify.mock.invocationCallOrder[0]).toBeLessThan(
    artifacts.markExpiring.mock.invocationCallOrder[0]!,
  );
  expect(artifacts.put).toHaveBeenCalledWith(
    `runs/${runId}/checkpoints/latest.json`,
    Buffer.from(JSON.stringify(checkpoint)),
    { expiring: true },
  );
  expect(artifacts.put).toHaveBeenCalledWith(
    `runs/${runId}/output/result.json`,
    expect.anything(),
    undefined,
  );
});

it("refuses to tag a reported checkpoint outside the run's checkpoints", async () => {
  const artifacts = fakeArtifacts();
  trainerReports("output/0/adapter.tar.gz");

  await expect(
    activities(artifacts).trainAdapter(
      runId,
      0,
      { url: "http://trainer" } as TrainingHost,
      dataset,
    ),
  ).rejects.toThrow("outside checkpoints");
  expect(artifacts.markExpiring).not.toHaveBeenCalled();
});
