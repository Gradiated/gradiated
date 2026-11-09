import { isDeepStrictEqual } from "node:util";

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

export const leaseRequestSchema = z.strictObject({
  holder: z.string().min(1).max(100),
  purpose: z.string().min(1).max(500),
  until: z.iso.datetime({ offset: true }),
  // A preemptible lease, the default, gives its host back when a model
  // replica has nowhere else to run. Always written, so a recorded request
  // compares equal to the annotation it came from.
  preemptible: z.boolean().default(true),
});

export const hostLeaseSchema = z.strictObject({
  holder: z.string(),
  purpose: z.string(),
  since: z.string(),
});

export const ROLLOUT_KINDS = [
  "enroll",
  "recover",
  "reimage",
  "bundle",
  "lease",
  "return",
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
  // The lease request a lease rollout was started for, or a return ended.
  // That request has had its outcome; the operator removes its annotation.
  lease: leaseRequestSchema.optional(),
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
  // Set while the host is leased: drained, cordoned and out of the pool.
  lease: hostLeaseSchema.optional(),
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
    extraTaints: z
      .array(z.object({ key: z.string(), value: z.string() }))
      .optional(),
  }),
  status: hostStatusSchema.optional(),
});

export type GpuHost = z.infer<typeof gpuHostSchema>;
export type HostStatus = z.infer<typeof hostStatusSchema>;
export type Condition = z.infer<typeof conditionSchema>;
export type Rollout = z.infer<typeof rolloutSchema>;
export type Bundle = z.infer<typeof bundleSchema>;
export type LeaseRequest = z.infer<typeof leaseRequestSchema>;
export type HostLease = z.infer<typeof hostLeaseSchema>;

// Set by a person (kubectl annotate) to restart a failed rollout.
export const RETRY_ANNOTATION = "fleet.gradiated.com/retry";
// A lease request as JSON (tools/gpu/host-lease.py); removing it hands the host back.
export const LEASE_ANNOTATION = "fleet.gradiated.com/lease";
export const RESERVED_TAINT = "gradiated.com/reserved";

// Whether the host's lease request already had its outcome, recorded on its
// last rollout: a lease that failed, or a return that ended it by expiry or
// preemption.
export const leaseEnded = (host: GpuHost) => {
  const request = leaseRequest(host);
  const last = host.status?.rollout;
  return (
    request !== undefined &&
    !("invalid" in request) &&
    !host.status?.lease &&
    last?.lease !== undefined &&
    ((last.kind === "lease" && last.result === "Failed") ||
      (last.kind === "return" && last.result === "Succeeded")) &&
    isDeepStrictEqual(last.lease, request)
  );
};

// What a host's GPUs are doing, for capacity: exactly one state per host.
// in_pool and reserved hosts serve models and take new replicas; cordoned
// hosts serve what already runs on them but take nothing new; the rest are
// out of the pool, on their way in or out of it, or broken.
export const HOST_STATES = [
  "in_pool",
  "leased",
  "reserved",
  "cordoned",
  "leasing",
  "returning",
  "updating",
  "degraded",
] as const;
export type HostState = (typeof HOST_STATES)[number];

export const hostState = (
  host: GpuHost,
  node?: { unschedulable: boolean },
): HostState => {
  const status = host.status;
  const rollout = status?.rollout;
  const running = rollout?.result === "Running";
  // Degraded wins over a lease or rollout, as gradiated_gpu_fleet_host_degraded
  // reports it. A failed return leaves the phase to the next reconcile.
  if (status?.phase === "Degraded") return "degraded";
  if (status?.lease) {
    if (rollout?.kind === "return" && rollout.result === "Failed")
      return "degraded";
    return running && rollout?.kind === "return" ? "returning" : "leased";
  }
  if (running) return rollout?.kind === "lease" ? "leasing" : "updating";
  const request = leaseRequest(host);
  // Requested and waiting for the operator to start draining it.
  if (request && !("invalid" in request) && !leaseEnded(host)) return "leasing";
  // Not seen yet (no phase, or Pending), or deleted with pods still on it
  // (Draining).
  if (status?.phase !== "Ready") return "updating";
  // Cordoned by a person; a rollout's own cordon is a running rollout above.
  if (node?.unschedulable) return "cordoned";
  return host.spec.extraTaints?.some((taint) => taint.key === RESERVED_TAINT)
    ? "reserved"
    : "in_pool";
};

export const leaseRequest = (
  host: GpuHost,
): LeaseRequest | { invalid: string } | undefined => {
  const value = host.metadata.annotations?.[LEASE_ANNOTATION];
  if (value === undefined) return undefined;

  try {
    const parsed = leaseRequestSchema.safeParse(JSON.parse(value));
    return parsed.success
      ? parsed.data
      : { invalid: parsed.error.issues[0]?.message ?? "invalid" };
  } catch {
    return { invalid: "not JSON" };
  }
};

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
