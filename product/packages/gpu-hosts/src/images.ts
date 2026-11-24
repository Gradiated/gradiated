import { z } from "zod";

const repository = String.raw`[a-z0-9.-]+\/[a-z0-9._/-]+`;
const inputTag = ":gpu-base-inputs-[0-9a-f]{64}";

// RunPod ECR delegation requires a tag. Input-hash tags identify immutable builds.
export const GpuBaseImageSchema = z
  .string()
  .regex(new RegExp(`^${repository}${inputTag}$`));

// AWS hosts pull with their own ECR credentials, so they can also run a build
// by digest; newer builds only carry suffixed input-hash tags.
export const AwsGpuBaseImageSchema = z
  .string()
  .regex(new RegExp(`^${repository}(${inputTag}|@sha256:[0-9a-f]{64})$`));

// The image's registry and repository, without its tag or digest.
export const gpuBaseRepository = (image: string) =>
  image.replace(/(:[^/:@]+|@sha256:[0-9a-f]{64})$/, "");
