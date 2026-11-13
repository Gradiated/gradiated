import {
  WorkloadBenchmarkSchema,
  type WorkloadBenchmark,
} from "@gradiated/contracts";
import {
  versionFileKey,
  type VersionFileRecord,
} from "./version-file-store.js";
import type { ObjectStorage } from "../storage/object-storage.js";

export const MAX_BENCHMARK_BYTES = 32_768;

export const parseWorkloadBenchmark = (bytes: Uint8Array) =>
  WorkloadBenchmarkSchema.safeParse(
    JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes)),
  );
const READ_CONCURRENCY = 8;

export const readWorkloadBenchmarks = async (
  files: VersionFileRecord[],
  storage: Pick<ObjectStorage, "read"> | undefined,
): Promise<Map<string, WorkloadBenchmark>> => {
  const benchmarks = new Map<string, WorkloadBenchmark>();
  if (!storage) return benchmarks;

  const pending = files
    .filter((file) => file.sizeBytes <= MAX_BENCHMARK_BYTES)
    .values();
  await Promise.all(
    Array.from(
      { length: Math.min(READ_CONCURRENCY, files.length) },
      async () => {
        for (const file of pending) {
          try {
            const bytes = await storage.read(versionFileKey(file), {
              maxBytes: MAX_BENCHMARK_BYTES,
              timeoutMs: 2_000,
            });
            const parsed = parseWorkloadBenchmark(bytes);
            if (parsed.success) benchmarks.set(file.versionId, parsed.data);
          } catch {
            // A missing or invalid optional artifact preserves automatic table stats.
          }
        }
      },
    ),
  );

  return benchmarks;
};
