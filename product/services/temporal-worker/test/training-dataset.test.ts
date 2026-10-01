import { createHash } from "node:crypto";
import { expect, it } from "vitest";
import { SftDatasetManifestSchema } from "@gradiated/contracts";
import type { buildSftDataset, TrainingArtifacts } from "@gradiated/control";
import { persistTrainingDataset } from "../src/training/dataset.js";

it.each([12, 80])(
  "records all split artifacts and the actual evaluation subset of %i test rows",
  async (count) => {
    const rows = (n: number) =>
      Buffer.from(
        Array.from({ length: n }, (_, id) =>
          JSON.stringify({
            id: String(id).padStart(3, "0"),
            group: String(id),
            prompt: [{ role: "user", content: "question" }],
            completion: [{ role: "assistant", content: "answer" }],
          }),
        ).join("\n") + "\n",
      );
    const objects = new Map<string, Buffer>();
    const artifacts = {
      put: async (key: string, bytes: Uint8Array) => {
        objects.set(key, Buffer.from(bytes));
        return {
          key,
          size_bytes: bytes.length,
          sha256: createHash("sha256").update(bytes).digest("hex"),
        };
      },
      uri: (key: string) => `s3://datasets/${key}`,
    } as TrainingArtifacts;
    const dataset: Awaited<ReturnType<typeof buildSftDataset>> = {
      files: { train: rows(10), validation: rows(2), test: rows(count) },
      summary: {
        eligible_examples: count + 12,
        duplicates_removed: 0,
        train: 10,
        validation: 2,
        test: count,
      },
      builder: {
        id: "gradiated-traces-sft",
        version: 1,
        split: {
          algorithm: "sha256_group_modulo_10",
          group_by: "session_and_shared_prompt",
          buckets: {
            train: [2, 3, 4, 5, 6, 7, 8, 9],
            validation: [1],
            test: [0],
          },
        },
        max_examples: 10000,
        max_content_bytes: 67108864,
      },
    };
    const saved = await persistTrainingDataset(
      artifacts,
      "runs/test/dataset/v1",
      dataset,
      "2026-09-29T00:00:00.000Z",
    );
    const manifest = SftDatasetManifestSchema.parse(
      JSON.parse(
        objects.get("runs/test/dataset/v1/dataset-manifest.json")!.toString(),
      ),
    );
    expect(manifest).not.toHaveProperty("provenance");
    expect(manifest).not.toHaveProperty("host");
    expect(manifest.splits.test.examples).toBe(count);
    expect(manifest.evaluation_sample!.examples).toBe(Math.min(count, 64));
    expect(saved.summary.evaluation_examples).toBe(Math.min(count, 64));
    expect(artifacts.uri(saved.evaluation.key)).not.toBe(
      manifest.splits.test.files[0]!.uri,
    );
    expect(
      objects.get(saved.evaluation.key)!.toString().trim().split("\n"),
    ).toEqual(dataset.files.test.toString().trim().split("\n").slice(0, 64));
    for (const split of [
      ...Object.values(manifest.splits),
      manifest.evaluation_sample!,
    ]) {
      for (const file of split.files) {
        const bytes = objects.get(file.uri.replace("s3://datasets/", ""))!;
        expect(file.size_bytes).toBe(bytes.length);
        expect(file.sha256).toBe(
          createHash("sha256").update(bytes).digest("hex"),
        );
        expect(split.examples).toBe(bytes.toString().trim().split("\n").length);
      }
    }
  },
);
