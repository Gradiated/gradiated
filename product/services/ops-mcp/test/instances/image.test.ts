import { readFileSync } from "node:fs";
import { expect, it } from "vitest";
import { GpuBaseImageSchema } from "../../src/instances/image.js";

it("keeps provisioning defaults in the RunPod-compatible immutable-tag format", () => {
  const template = JSON.parse(
    readFileSync(
      new URL(
        "../../../../../infra/environments/prod/runpod/templates.json",
        import.meta.url,
      ),
      "utf8",
    ),
  ) as { image: string };
  const workload = readFileSync(
    new URL(
      "../../../../../infra/environments/prod/us-east-1/kubernetes/operations/ops-mcp/workload.yaml",
      import.meta.url,
    ),
    "utf8",
  );
  const deployed = workload.match(/name: GPU_BASE_IMAGE\s+value: (\S+)/)?.[1];
  expect(GpuBaseImageSchema.parse(template.image)).toBe(deployed);
  for (const image of [
    template.image.split(":")[0] + ":latest",
    template.image.split(":")[0] + "@sha256:" + "a".repeat(64),
    template.image + "@sha256:" + "a".repeat(64),
  ])
    expect(GpuBaseImageSchema.safeParse(image).success).toBe(false);
});
