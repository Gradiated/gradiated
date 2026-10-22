import { GPU_HOSTS, hostName, NODES, PODS, type GpuHost } from "./hosts.js";
import type { Kubernetes } from "./kubernetes.js";

// Holds a deleted GpuHost until no pod runs on its node, so retiring a host
// cannot drop serving pods. Argo never prunes GpuHosts; deletion is explicit.
export const DRAIN_FINALIZER = "fleet.gradiated.com/drain";

const finalizers = (host: GpuHost) => host.metadata.finalizers ?? [];

// The resourceVersion makes each finalizer change a conditional update, so a
// concurrent change to the list fails with 409 instead of being overwritten.
const setFinalizers = (api: Kubernetes, host: GpuHost, next: string[]) =>
  api.mergePatch(`${GPU_HOSTS}/${host.metadata.name}`, {
    metadata: {
      finalizers: next,
      resourceVersion: host.metadata.resourceVersion,
    },
  });

export const holdUntilDrained = async (api: Kubernetes, host: GpuHost) => {
  if (
    host.metadata.deletionTimestamp ||
    finalizers(host).includes(DRAIN_FINALIZER)
  )
    return false;

  await setFinalizers(api, host, [...finalizers(host), DRAIN_FINALIZER]);
  return true;
};

const runningPods = async (api: Kubernetes, host: GpuHost) => {
  const node = encodeURIComponent(
    `spec.nodeName=${hostName(host.spec.instanceId)}`,
  );
  const pods = (await api.list(`${PODS}?fieldSelector=${node}`)) as {
    status?: { phase?: string };
  }[];
  return pods.filter(
    (pod) => !["Succeeded", "Failed"].includes(pod.status?.phase ?? ""),
  ).length;
};

// Marks cordons the operator made, so it undoes only those when a host returns
// and never a cordon someone applied by hand.
export const CORDONED_BY = "fleet.gradiated.com/cordoned-by";

type Node = {
  metadata?: { annotations?: Record<string, string> };
  spec?: { unschedulable?: boolean };
};

const nodePath = (host: GpuHost) =>
  `${NODES}/${hostName(host.spec.instanceId)}`;

// Returns whether the node was already cordoned before this call. A missing
// node cannot receive pods, so it counts as cordoned.
const cordon = async (api: Kubernetes, host: GpuHost) => {
  const node = (await api.get(nodePath(host))) as Node | undefined;
  if (!node || node.spec?.unschedulable) return true;

  await api.mergePatch(nodePath(host), {
    metadata: { annotations: { [CORDONED_BY]: "gpu-fleet" } },
    spec: { unschedulable: true },
  });
  return false;
};

// A host added back after a retirement keeps the cordon its drain left.
export const uncordonIfReturned = async (api: Kubernetes, host: GpuHost) => {
  const node = (await api.get(nodePath(host))) as Node | undefined;
  if (node?.metadata?.annotations?.[CORDONED_BY] !== "gpu-fleet") return false;

  await api.mergePatch(nodePath(host), {
    metadata: { annotations: { [CORDONED_BY]: null } },
    spec: { unschedulable: false },
  });
  return true;
};

// The host is released only once its node was cordoned on an earlier pass and
// no pods remain, so a pod the scheduler placed just before the cordon is
// counted before release.
export const releaseIfDrained = async (api: Kubernetes, host: GpuHost) => {
  const cordoned = await cordon(api, host);
  const remaining = await runningPods(api, host);
  const released = cordoned && remaining === 0;
  if (released && finalizers(host).includes(DRAIN_FINALIZER))
    await setFinalizers(
      api,
      host,
      finalizers(host).filter((name) => name !== DRAIN_FINALIZER),
    );
  return { remaining, released };
};
