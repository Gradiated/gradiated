import { z } from "zod";

export const GPU_HOSTS = "/apis/fleet.gradiated.com/v1alpha1/gpuhosts";
export const SERVICES = "/api/v1/namespaces/tailscale-inference/services";
export const PODS = "/api/v1/namespaces/gpu-inference/pods";
export const NODES = "/api/v1/nodes";
export const TAILNET = "tail186117.ts.net";

const conditionSchema = z.object({
  type: z.enum(["Ready", "Degraded"]),
  status: z.enum(["True", "False", "Unknown"]),
  reason: z.string().optional(),
  message: z.string().optional(),
  lastTransitionTime: z.string(),
});

export const hostStatusSchema = z.object({
  observedGeneration: z.number().int().optional(),
  phase: z.enum(["Pending", "Ready", "Degraded", "Draining"]).optional(),
  observed: z
    .object({
      reachable: z.boolean().optional(),
      lastSeen: z.string().optional(),
      hostBundleSha256: z.string().optional(),
    })
    .optional(),
  conditions: z.array(conditionSchema).optional(),
});

// Bounds and patterns are enforced by the CRD at admission
// (gpu-inference/gpuhost-crd.yaml); this reads the fields the operator uses.
export const gpuHostSchema = z.object({
  metadata: z.object({
    name: z.string(),
    uid: z.string().min(1),
    resourceVersion: z.string().optional(),
    generation: z.number().int().optional(),
    creationTimestamp: z.string().optional(),
    deletionTimestamp: z.string().optional(),
    finalizers: z.array(z.string()).optional(),
  }),
  spec: z.object({
    instanceId: z.uuid(),
    provider: z.object({
      name: z.literal("runpod"),
      accountId: z.string(),
      podId: z.string(),
      machineId: z.string().optional(),
    }),
    inventory: z.object({
      gpuProduct: z.string(),
      gpuCount: z.number().int(),
      cpu: z.number().int(),
      memoryGiB: z.number().int(),
    }),
  }),
  status: hostStatusSchema.optional(),
});

export type GpuHost = z.infer<typeof gpuHostSchema>;
export type HostStatus = z.infer<typeof hostStatusSchema>;
export type Condition = z.infer<typeof conditionSchema>;

export const hostName = (instanceId: string) => `gpu-${instanceId}`;

export const hostEndpoint = (instanceId: string) =>
  `http://${hostName(instanceId)}.tailscale-inference.svc.cluster.local:8888/_kubelet`;

export const parseHosts = (items: unknown[]) => {
  const hosts: GpuHost[] = [];
  const invalid: { name: string; reported: boolean }[] = [];
  for (const item of items) {
    const parsed = gpuHostSchema.safeParse(item);
    if (
      parsed.success &&
      parsed.data.metadata.name === hostName(parsed.data.spec.instanceId)
    )
      hosts.push(parsed.data);
    else {
      const { metadata, status } = item as {
        metadata?: { name?: unknown };
        status?: { conditions?: { reason?: string; status?: string }[] };
      };
      invalid.push({
        name: typeof metadata?.name === "string" ? metadata.name : "",
        reported: Boolean(
          status?.conditions?.some(
            (condition) =>
              condition.reason === "InvalidSpec" && condition.status === "True",
          ),
        ),
      });
    }
  }
  return { hosts, invalid };
};
