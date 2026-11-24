import { readFileSync } from "node:fs";
import { expect, it } from "vitest";
import {
  artifactAccount,
  AwsGpuBaseImageSchema,
  GpuBaseImageSchema,
  gpuBaseRepository,
} from "../../src/instances/image.js";

const workload = readFileSync(
  new URL(
    "../../../../../infra/environments/prod/us-east-1/kubernetes/operations/ops-mcp/workload.yaml",
    import.meta.url,
  ),
  "utf8",
);
const deployed = (name: string) =>
  workload.match(new RegExp(`- name: ${name}\\s+value: (\\S+)`))?.[1];
const repository =
  "873716897517.dkr.ecr.us-east-1.amazonaws.com/gradiated/prod/inference";

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
  expect(GpuBaseImageSchema.parse(template.image)).toBe(
    deployed("GPU_BASE_IMAGE"),
  );
  for (const image of [
    template.image.split(":")[0] + ":latest",
    template.image.split(":")[0] + "@sha256:" + "a".repeat(64),
    template.image + "@sha256:" + "a".repeat(64),
    template.image + "-e26750f896ea",
  ])
    expect(GpuBaseImageSchema.safeParse(image).success).toBe(false);
});

it("lets AWS hosts run an input-hash tag or a digest, but nothing mutable", () => {
  for (const image of [
    `${repository}:gpu-base-inputs-${"a".repeat(64)}`,
    `${repository}@sha256:${"b".repeat(64)}`,
  ])
    expect(AwsGpuBaseImageSchema.safeParse(image).success).toBe(true);
  for (const image of [
    `${repository}:latest`,
    `${repository}:gpu-base-inputs-${"a".repeat(64)}-e26750f896ea`,
    `${repository}:gpu-base-inputs-${"a".repeat(64)}@sha256:${"b".repeat(64)}`,
    `${repository}@sha256:${"b".repeat(63)}`,
    `${repository}@sha512:${"b".repeat(64)}`,
    `${repository}`,
  ])
    expect(AwsGpuBaseImageSchema.safeParse(image).success).toBe(false);
});

it("deploys an AWS image by digest from the RunPod image's repository and artifact account", () => {
  const shared = GpuBaseImageSchema.parse(deployed("GPU_BASE_IMAGE"));
  const aws = AwsGpuBaseImageSchema.parse(deployed("AWS_GPU_BASE_IMAGE"));
  expect(aws).toMatch(/@sha256:[0-9a-f]{64}$/);
  expect(gpuBaseRepository(aws)).toBe(repository);
  expect(gpuBaseRepository(shared)).toBe(repository);
  expect(artifactAccount(aws)).toBe("873716897517");
  expect(artifactAccount(shared)).toBe("873716897517");
});

it("refuses an image outside an ECR registry for the artifact account", () => {
  expect(() =>
    artifactAccount(`registry.example/gpu-base@sha256:${"a".repeat(64)}`),
  ).toThrow("artifact account");
});
