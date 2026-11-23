import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

import type { GpuHost } from "../src/hosts.js";
import { pinnedImage, pinsSchema } from "../src/pins.js";

const repository =
  "873716897517.dkr.ecr.us-east-1.amazonaws.com/gradiated/prod/inference";
const base = {
  image: `${repository}:gpu-base-inputs-${"a".repeat(64)}`,
  imageDigest: `sha256:${"b".repeat(64)}`,
  hostBundle: { sha256: "c".repeat(64), baseId: "v3" },
};
const host = (name: "aws" | "runpod") =>
  ({ spec: { provider: { name } } }) as unknown as GpuHost;

describe("pins", () => {
  it("gives AWS hosts the AWS image, and every host the image without one", () => {
    const aws = `${repository}@sha256:${"d".repeat(64)}`;
    const pins = pinsSchema.parse({ ...base, awsImage: aws });

    expect(pinnedImage(pins, host("aws"))).toBe(aws);
    expect(pinnedImage(pins, host("runpod"))).toBe(base.image);
    expect(pinnedImage(pinsSchema.parse(base), host("aws"))).toBe(base.image);
  });

  it("refuses an AWS image that is mutable or in another repository", () => {
    for (const awsImage of [
      `${repository}:latest`,
      `${repository}/other@sha256:${"d".repeat(64)}`,
      `873716897517.dkr.ecr.us-east-1.amazonaws.com/other:gpu-base-inputs-${"a".repeat(64)}`,
    ])
      expect(pinsSchema.safeParse({ ...base, awsImage }).success).toBe(false);
  });

  it("pins AWS hosts to the build ops-mcp registers them with", () => {
    const read = (path: string) =>
      readFileSync(new URL(path, import.meta.url), "utf8");
    const pins = pinsSchema.parse(
      JSON.parse(
        read(
          "../../../../infra/environments/prod/us-east-1/kubernetes/gpu-inference/pins.json",
        ),
      ),
    );
    const workload = read(
      "../../../../infra/environments/prod/us-east-1/kubernetes/operations/ops-mcp/workload.yaml",
    );

    expect(pins.awsImage).toBe(
      workload.match(/- name: AWS_GPU_BASE_IMAGE\s+value: (\S+)/)?.[1],
    );
  });
});
