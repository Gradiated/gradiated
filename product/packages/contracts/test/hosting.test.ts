import { expect, it } from "vitest";

import { TaskVersionAdapterSchema } from "../src/training.js";

const hash = "a".repeat(64);

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
