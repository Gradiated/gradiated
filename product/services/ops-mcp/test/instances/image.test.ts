import { expect, it } from "vitest";
import {
  artifactAccount,
  AwsGpuBaseImageSchema,
  GpuBaseImageSchema,
  gpuBaseRepository,
} from "../../src/instances/image.js";

const repository =
  "873716897517.dkr.ecr.us-east-1.amazonaws.com/gradiated/prod/inference";
const runpodImage = `${repository}:gpu-base-inputs-${"a".repeat(64)}`;
const awsImage = `${repository}@sha256:${"b".repeat(64)}`;

it("keeps provisioning defaults in the RunPod-compatible immutable-tag format", () => {
  expect(GpuBaseImageSchema.parse(runpodImage)).toBe(runpodImage);
  for (const image of [
    repository + ":latest",
    repository + "@sha256:" + "a".repeat(64),
    runpodImage + "@sha256:" + "a".repeat(64),
    runpodImage + "-e26750f896ea",
  ])
    expect(GpuBaseImageSchema.safeParse(image).success).toBe(false);
});

it("lets AWS hosts run an input-hash tag or a digest, but nothing mutable", () => {
  for (const image of [runpodImage, awsImage])
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
  const shared = GpuBaseImageSchema.parse(runpodImage);
  const aws = AwsGpuBaseImageSchema.parse(awsImage);
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
