import { z } from "zod";

export const GPU_HOSTS = "/apis/fleet.gradiated.com/v1alpha1/gpuhosts";
export const SERVICES = "/api/v1/namespaces/tailscale-inference/services";
export const PODS = "/api/v1/namespaces/gpu-inference/pods";
export const NODES = "/api/v1/nodes";
export const ROLLOUTS =
  "/apis/argoproj.io/v1alpha1/namespaces/gpu-inference/rollouts";
export const SCALED_OBJECTS =
  "/apis/keda.sh/v1alpha1/namespaces/gpu-inference/scaledobjects";
export const TAILNET = "tail186117.ts.net";

const conditionSchema = z.object({
  type: z.enum(["Ready", "Degraded"]),
  status: z.enum(["True", "False", "Unknown"]),
  reason: z.string().optional(),
  message: z.string().optional(),
  lastTransitionTime: z.string(),
});

const bundleSchema = z.object({ sha256: z.string(), baseId: z.string() });

export const ROLLOUT_KINDS = [
  "enroll",
  "recover",
  "reimage",
  "bundle",
] as const;
export const ROLLOUT_RESULTS = [
  "Running",
  "Succeeded",
  "Failed",
  "Blocked",
] as const;

// Written only by the operator. The controller applies `bundle` to the host.
export const rolloutSchema = z.object({
  kind: z.enum(ROLLOUT_KINDS),
  target: z.object({ image: z.string(), bundle: bundleSchema }),
  step: z.string(),
  result: z.enum(ROLLOUT_RESULTS),
  startedAt: z.string(),
  stepStartedAt: z.string(),
  finishedAt: z.string().optional(),
  // How many times in a row this target has blocked on this host; each retry
  // waits twice as long as the one before.
  blockedCount: z.number().int().optional(),
  lastError: z.string().optional(),
  // The retry annotation value this rollout was started for.
  retry: z.string().optional(),
  surge: z
    .array(
      z.object({
        model: z.string(),
        replicas: z.number().int(),
        extra: z.number().int(),
      }),
    )
    .optional(),
  // Serving pod UID → qualified runtime incarnation before an in-place update.
  baseline: z.record(z.string(), z.string()).optional(),
  // Recorded before RunPod is asked to re-image the pod.
  reimageRequestedAt: z.string().optional(),
  // Recorded before enrollment starts, with the operator replica running it.
  enrollStartedAt: z.string().optional(),
  enrollBy: z.string().optional(),
  enrolledAt: z.string().optional(),
  healthySince: z.string().optional(),
  bootstrapAddress: z.string().optional(),
  // IDs, never values, of the single-use keys this rollout minted.
  keys: z.array(z.string()).optional(),
  bundle: bundleSchema.optional(),
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
  plan: z.string().optional(),
  rollout: rolloutSchema.optional(),
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
    annotations: z.record(z.string(), z.string()).optional(),
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
    managementSecret: z.object({
      key: z.string(),
      property: z.string().optional(),
    }),
  }),
  status: hostStatusSchema.optional(),
});

export type GpuHost = z.infer<typeof gpuHostSchema>;
export type HostStatus = z.infer<typeof hostStatusSchema>;
export type Condition = z.infer<typeof conditionSchema>;
export type Rollout = z.infer<typeof rolloutSchema>;
export type Bundle = z.infer<typeof bundleSchema>;

// Set by a person (kubectl annotate) to restart a failed rollout.
export const RETRY_ANNOTATION = "fleet.gradiated.com/retry";

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
