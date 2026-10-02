import { createHash } from "node:crypto";
import { expect, it, vi } from "vitest";
import { createAdapterDownloads } from "../src/training/downloads.js";
import { ObjectStorage } from "../src/storage/object-storage.js";

const runId = "01a0f891-4533-717c-81a9-24c5833d42e8";
const rows = [
  {
    id: "example",
    group: "group",
    fine_tuned: { text: "144", tokens: 3, seconds: 1 },
    comparison: { text: "144", tokens: 3, seconds: 1 },
    judgment: "TIE",
    fine_tuned_first: true,
  },
];

const fixture = (overrides: Record<string, unknown> = {}) => {
  const bytes = Buffer.from(JSON.stringify(rows));
  const manifest = {
    key: `runs/${runId}/evaluation/1/predictions.json`,
    size_bytes: bytes.length,
    sha256: createHash("sha256").update(bytes).digest("hex"),
    ...overrides,
  };
  const storage = new ObjectStorage("artifacts");
  const read = vi
    .spyOn(storage, "read")
    .mockResolvedValueOnce(Buffer.from(JSON.stringify(manifest)))
    .mockResolvedValueOnce(bytes);

  return { storage, read };
};

it("reads verified prediction pairs from the run-scoped manifest", async () => {
  const { storage, read } = fixture();
  expect(await createAdapterDownloads(storage).results!(runId)).toEqual(rows);
  expect(read.mock.calls[0]?.[0]).toBe(`runs/${runId}/evaluation/result.json`);
});

it.each([
  { key: "runs/other/evaluation/predictions.json" },
  { key: `runs/${runId}/evaluation/../private.json` },
  { sha256: "0".repeat(64) },
  { size_bytes: 1 },
])("rejects foreign or corrupt artifacts %j", async (overrides) => {
  const { storage } = fixture(overrides);
  await expect(createAdapterDownloads(storage).results!(runId)).rejects.toThrow(
    "Evaluation results could not be loaded",
  );
});
