import { z } from "zod";

import { hostName, NODES, PODS, ROLLOUTS, SCALED_OBJECTS } from "./hosts.js";
import { CORDONED_BY } from "./drain.js";
import type { Kubernetes } from "./kubernetes.js";
import {
  podPlacementSchema,
  POD_NAMESPACE,
  type PodPlacement,
  type NodePlacement,
} from "./placement.js";

const MODEL_LABEL = "app.kubernetes.io/name";
const QUALIFIED_RUNTIME = "gradiated.com/qualified-runtime";
const QUALIFICATION_ERROR = "gradiated.com/qualification-error";
// KEDA scales the target to this count and stops autoscaling while it is set.
export const PAUSED_REPLICAS = "autoscaling.keda.sh/paused-replicas";
const GPU_RESOURCE = "nvidia.com/gpu";
// The ReplicaSet controller removes the pod with the lowest cost first.
export const DELETION_COST = "controller.kubernetes.io/pod-deletion-cost";

// Only fields the operator reads are checked. Unset fields arrive as null
// (gpu-controller sends null condition times), so optional fields accept it.
const podSchema = z.object({
  metadata: z.object({
    name: z.string(),
    uid: z.string(),
    namespace: z.string().nullish(),
    labels: z.record(z.string(), z.string()).nullish(),
    annotations: z.record(z.string(), z.string()).nullish(),
    deletionTimestamp: z.string().nullish(),
    ownerReferences: z
      .array(z.object({ kind: z.string(), name: z.string() }))
      .nullish(),
  }),
  spec: z
    .object({
      ...podPlacementSchema.shape,
      nodeName: z.string().nullish(),
      containers: z
        .array(
          z.object({
            resources: z
              .object({
                requests: z.record(z.string(), z.string()).nullish(),
                limits: z.record(z.string(), z.string()).nullish(),
              })
              .nullish(),
          }),
        )
        .nullish(),
    })
    .nullish(),
  status: z
    .object({
      phase: z.string().nullish(),
      conditions: z
        .array(
          z.object({
            type: z.string(),
            status: z.string(),
            reason: z.string().nullish(),
            lastTransitionTime: z.string().nullish(),
          }),
        )
        .nullish(),
      containerStatuses: z
        .array(z.object({ containerID: z.string().nullish() }))
        .nullish(),
    })
    .nullish(),
});

export type ClusterPod = {
  name: string;
  uid: string;
  namespace?: string;
  labels?: Record<string, string>;
  model?: string;
  modelId?: string;
  training: boolean;
  node?: string;
  ready: boolean;
  terminating: boolean;
  gpus: number;
  placement?: PodPlacement;
  // Since when the scheduler has found no node for it.
  unschedulableSince?: string;
  qualifiedRuntime?: string;
  // SDK qualification rejected the running container. The worker never
  // retries that container, so the pod cannot become Ready until it restarts.
  qualificationFailed: boolean;
};

// An unreadable pod fails the whole read: dropping it would make a serving
// host look empty, and the operator would re-image or release it.
export class UnreadablePod extends Error {}

const parsePod = (item: unknown) => {
  const parsed = podSchema.safeParse(item);
  if (parsed.success) return parsed.data;

  const name = (item as { metadata?: { name?: unknown } } | undefined)?.metadata
    ?.name;
  const issues = parsed.error.issues
    .map((issue) => `${issue.path.join(".")}: ${issue.message}`)
    .join("; ");
  throw new UnreadablePod(
    `Pod ${typeof name === "string" ? name : "(unnamed)"} cannot be read: ${issues}`,
  );
};

export const clusterPod = (item: unknown): ClusterPod | undefined => {
  const { metadata, spec, status } = parsePod(item);
  if (["Succeeded", "Failed"].includes(status?.phase ?? "")) return;

  const condition = (type: string) =>
    status?.conditions?.find((entry) => entry.type === type);
  const scheduled = condition("PodScheduled");
  const incarnation = status?.containerStatuses?.[0]?.containerID;
  const modelId =
    metadata.annotations?.["gradiated.com/serving-model-id"] ??
    metadata.annotations?.["gradiated.com/model-id"];
  const placement = podPlacementSchema.parse(spec ?? {});
  return {
    name: metadata.name,
    uid: metadata.uid,
    namespace: metadata.namespace ?? POD_NAMESPACE,
    labels: metadata.labels ?? {},
    ...(modelId && { modelId }),
    ...(metadata.labels?.[MODEL_LABEL] &&
      metadata.ownerReferences?.some(
        (owner) => owner.kind === "ReplicaSet",
      ) && {
        model: metadata.labels[MODEL_LABEL],
      }),
    training:
      metadata.annotations?.["gradiated.com/workload-kind"] === "training",
    ...(spec?.nodeName && { node: spec.nodeName }),
    ready: condition("Ready")?.status === "True",
    terminating: Boolean(metadata.deletionTimestamp),
    gpus: (spec?.containers ?? []).reduce(
      (sum, { resources }) =>
        sum +
        Number(
          resources?.limits?.[GPU_RESOURCE] ??
            resources?.requests?.[GPU_RESOURCE] ??
            0,
        ),
      0,
    ),
    ...(Object.values(placement).some((value) => value != null) && {
      placement,
    }),
    ...(scheduled?.status === "False" &&
      scheduled.reason === "Unschedulable" && {
        unschedulableSince: scheduled.lastTransitionTime ?? "",
      }),
    ...(metadata.annotations?.[QUALIFIED_RUNTIME] && {
      qualifiedRuntime: metadata.annotations[QUALIFIED_RUNTIME],
    }),
    qualificationFailed: Boolean(
      incarnation &&
      metadata.annotations?.[QUALIFICATION_ERROR] === incarnation,
    ),
  };
};

const selector = (key: string, value: string) =>
  encodeURIComponent(`${key}=${value}`);

export type NodeState = NodePlacement & {
  ready: boolean;
  unschedulable: boolean;
  // The cordon is a rollout's own, not a person's or the drain's.
  cordonedByRollout?: boolean;
};

// The value of the drain's CORDONED_BY marker for a rollout's cordon.
export const ROLLOUT_CORDON = "gpu-fleet-rollout";

type Node = {
  metadata?: { resourceVersion?: string; annotations?: Record<string, string> };
  spec?: { unschedulable?: boolean };
};

export const createCluster = (
  api: Kubernetes,
  log: (event: Record<string, unknown>) => void,
) => {
  const nodePath = (instanceId: string) => `${NODES}/${hostName(instanceId)}`;
  const clusterPods = (items: unknown[]) => {
    try {
      return items
        .map(clusterPod)
        .filter((pod): pod is ClusterPod => pod !== undefined);
    } catch (error) {
      if (error instanceof UnreadablePod)
        log({
          event: "gpu_fleet_pod_unreadable",
          level: "warn",
          error: error.message,
        });
      throw error;
    }
  };

  return {
    node: async (instanceId: string): Promise<NodeState | undefined> => {
      const node = (await api.get(nodePath(instanceId))) as
        | {
            metadata?: {
              name?: string;
              labels?: Record<string, string>;
              annotations?: Record<string, string>;
            };
            spec?: {
              unschedulable?: boolean;
              taints?: NodePlacement["taints"];
            };
            status?: { conditions?: { type: string; status: string }[] };
          }
        | undefined;
      if (!node) return;

      return {
        ready:
          node.status?.conditions?.find((entry) => entry.type === "Ready")
            ?.status === "True",
        unschedulable: Boolean(node.spec?.unschedulable),
        cordonedByRollout:
          Boolean(node.spec?.unschedulable) &&
          node.metadata?.annotations?.[CORDONED_BY] === ROLLOUT_CORDON,
        ...(node.metadata?.name && { name: node.metadata.name }),
        labels: node.metadata?.labels ?? {},
        taints: node.spec?.taints ?? [],
      };
    },

    // A rollout cordons with its own marker, which the drain's
    // uncordonIfReturned leaves alone, and uncordons only a node it marked.
    // A node someone else cordoned stays as it is. The resourceVersion stops a
    // cordon applied between the read and the patch from being overwritten.
    cordon: async (instanceId: string) => {
      const node = (await api.get(nodePath(instanceId))) as Node | undefined;
      if (!node || node.spec?.unschedulable) return;
      await api.mergePatch(nodePath(instanceId), {
        metadata: {
          resourceVersion: node.metadata?.resourceVersion,
          annotations: { [CORDONED_BY]: ROLLOUT_CORDON },
        },
        spec: { unschedulable: true },
      });
    },

    uncordon: async (instanceId: string) => {
      const node = (await api.get(nodePath(instanceId))) as Node | undefined;
      if (node?.metadata?.annotations?.[CORDONED_BY] !== ROLLOUT_CORDON) return;
      await api.mergePatch(nodePath(instanceId), {
        metadata: {
          resourceVersion: node.metadata.resourceVersion,
          annotations: { [CORDONED_BY]: null },
        },
        spec: { unschedulable: false },
      });
    },

    podsOn: async (instanceId: string) =>
      clusterPods(
        await api.list(
          `${PODS}?fieldSelector=${selector("spec.nodeName", hostName(instanceId))}`,
        ),
      ),

    // Model pods the scheduler has not placed.
    unscheduledModelPods: async () =>
      clusterPods(
        await api.list(
          `${PODS}?fieldSelector=${selector("spec.nodeName", "")}`,
        ),
      ).filter((pod) => pod.model),

    modelPods: async (model: string) =>
      clusterPods(
        await api.list(`${PODS}?labelSelector=${selector(MODEL_LABEL, model)}`),
      ).filter((pod) => pod.model === model),

    replicas: async (model: string) => {
      const rollout = (await api.get(`${ROLLOUTS}/${model}`)) as
        { spec?: { replicas?: number } } | undefined;
      if (rollout?.spec?.replicas === undefined)
        throw new Error(`Rollout ${model} has no replica count`);
      return rollout.spec.replicas;
    },

    // Sets or clears KEDA's paused replica count, writing only on a change.
    pauseScaling: async (model: string, replicas: number | null) => {
      const scaled = (await api.get(`${SCALED_OBJECTS}/${model}`)) as
        { metadata?: { annotations?: Record<string, string> } } | undefined;
      if (!scaled) throw new Error(`ScaledObject ${model} is missing`);

      const current = scaled.metadata?.annotations?.[PAUSED_REPLICAS] ?? null;
      const wanted = replicas === null ? null : String(replicas);
      if (current !== wanted)
        await api.mergePatch(`${SCALED_OBJECTS}/${model}`, {
          metadata: { annotations: { [PAUSED_REPLICAS]: wanted } },
        });
    },

    removeFirst: (pod: ClusterPod) =>
      api.mergePatch(`${PODS}/${pod.name}`, {
        metadata: { annotations: { [DELETION_COST]: "-10000" } },
      }),
  };
};

export type Cluster = ReturnType<typeof createCluster>;
