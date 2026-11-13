import { expect, it, vi } from "vitest";
import { readWorkloadBenchmarks } from "../src/training/workload-benchmarks.js";
import type { VersionFileRecord } from "../src/training/version-file-store.js";

const benchmark = {
  schema_version: 1,
  comparison_model_id: null,
  workload: "Tool selection",
  notes: "",
  cost: null,
  speed: null,
  quality: null,
};
const file = (id: number): VersionFileRecord => ({
  id: `0198ae50-94d8-7d4d-a8be-${String(id).padStart(12, "0")}`,
  workspaceId: "0198ae50-94d8-7d4d-a8be-9f9b44b8c774",
  versionId: `0198ae50-94d8-7d4d-a8be-${String(id + 100).padStart(12, "0")}`,
  name: "benchmark.json",
  contentType: "application/json",
  sizeBytes: 500,
  status: "ready",
  createdAt: new Date(),
  completedAt: new Date(),
});

it("returns valid benchmarks by version and skips invalid or unavailable optional artifacts", async () => {
  const files = [file(1), file(2), file(3), { ...file(4), sizeBytes: 40_000 }];
  const read = vi
    .fn()
    .mockResolvedValueOnce(Buffer.from(JSON.stringify(benchmark)))
    .mockResolvedValueOnce(Buffer.from('{"schema_version":99}'))
    .mockRejectedValueOnce(new Error("unavailable"));
  const results = await readWorkloadBenchmarks(files, { read });
  expect([...results.entries()]).toEqual([[files[0]!.versionId, benchmark]]);
  expect(read).toHaveBeenCalledTimes(3);
  expect(read).toHaveBeenCalledWith(
    `version-files/${files[0]!.versionId}/${files[0]!.id}`,
    { maxBytes: 32768, timeoutMs: 2000 },
  );
});

it("bounds storage concurrency across large task lists", async () => {
  let active = 0;
  let maximum = 0;
  const read = vi.fn(async () => {
    maximum = Math.max(maximum, ++active);
    await new Promise((resolve) => setTimeout(resolve, 1));
    active--;
    return Buffer.from(JSON.stringify(benchmark));
  });
  const results = await readWorkloadBenchmarks(
    Array.from({ length: 25 }, (_, i) => file(i)),
    { read },
  );
  expect(results.size).toBe(25);
  expect(maximum).toBe(8);
});

it("preserves automatic stats when storage is not configured", async () => {
  expect((await readWorkloadBenchmarks([file(1)], undefined)).size).toBe(0);
});
