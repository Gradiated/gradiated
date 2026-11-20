import { z } from "zod";

// A host's provider instance ID names its bootstrap tailnet device,
// gpu-bootstrap-<id>: a RunPod pod ID or an EC2 instance ID.
export const RUNPOD_POD_ID = /^[a-z0-9]{1,40}$/;
export const EC2_INSTANCE_ID = /^i-[0-9a-f]{8,17}$/;

export const isProviderInstanceId = (id: string) =>
  RUNPOD_POD_ID.test(id) || EC2_INSTANCE_ID.test(id);

export const providerInstanceId = z
  .string()
  .refine(isProviderInstanceId, "Invalid RunPod pod or EC2 instance ID");
