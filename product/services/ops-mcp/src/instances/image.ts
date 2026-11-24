export {
  AwsGpuBaseImageSchema,
  GpuBaseImageSchema,
  gpuBaseRepository,
} from "@gradiated/gpu-hosts";

// The AWS account whose ECR registry, and so artifact bucket, holds the image.
export const artifactAccount = (image: string) => {
  const account = image.match(/^(\d{12})\.dkr\.ecr\./)?.[1];
  if (!account)
    throw new Error("GPU base image must identify its artifact account");
  return account;
};
