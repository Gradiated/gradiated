import { describe, expect, it } from "vitest";

import { adapterRuntimeName } from "../src/hosting.js";
import { TaskVersionAdapterSchema } from "../src/training.js";

const versionId = "01980000-0000-7000-8000-000000000001";
const hash = "a".repeat(64);

describe("immutable runtime adapter identity", () => {
  it("keeps different weights and versions in separate runtime namespaces", () => {
    expect(adapterRuntimeName(versionId, hash)).toBe(`ft-${versionId}-${hash}`);
    expect(adapterRuntimeName(versionId, hash)).not.toEqual(
      adapterRuntimeName(versionId, "b".repeat(64)),
    );
    expect(adapterRuntimeName(versionId, hash)).not.toEqual(
      adapterRuntimeName("01980000-0000-7000-8000-000000000002", hash),
    );
  });

  it.each([
    ["../../adapter", hash],
    [versionId, "../../adapter"],
    [versionId, "a".repeat(63)],
  ])("rejects invalid task-version identity %s / %s", (id, checksum) => {
    expect(() => adapterRuntimeName(id, checksum)).toThrow();
  });
});

it("keeps existing training artifacts readable without a recorded base revision", () => {
  const artifact = {
    format: "peft_lora",
    artifact_uri: "s3://artifacts/adapter.tar.gz",
    sha256: hash,
    size_bytes: 1024,
    rank: 2,
  };

  expect(TaskVersionAdapterSchema.parse(artifact)).toEqual(artifact);
  expect(
    TaskVersionAdapterSchema.parse({
      ...artifact,
      base_model_revision: "base-revision-1",
    }).base_model_revision,
  ).toBe("base-revision-1");
});
