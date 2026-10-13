import { z } from "zod";

// RunPod ECR delegation requires a tag. Input-hash tags identify immutable builds.
export const GpuBaseImageSchema = z
  .string()
  .regex(/^[a-z0-9.-]+\/[a-z0-9._/-]+:gpu-base-inputs-[0-9a-f]{64}$/);
