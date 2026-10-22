import type { InstanceTailnet, RunPod } from "@gradiated/gpu-hosts";

import type { NodeState } from "./cluster.js";
import type { GpuHost, Rollout } from "./hosts.js";
import type { Observation } from "./observe.js";
import type { Pins } from "./pins.js";

// A new GpuHost gets this long to answer before it is treated as never enrolled.
export const ENROLL_AFTER_MS = 10 * 60_000;
// A restarted container keeps its tailnet identity and rejoins well within
// this; one that has not by then was wiped.
export const REJOIN_WITHIN_MS = 10 * 60_000;
const RESTART_SLACK_MS = 60_000;

export type HostFacts = {
  host: GpuHost;
  observation: Observation;
  // Undefined when RunPod could not be read.
  pod?: RunPod;
  // Undefined when Tailscale could not be read.
  tailnet?: InstanceTailnet;
  node?: NodeState;
  // Model pods bound to the host and not terminating.
  servingPods: number;
  trainingPods: number;
  // Every pod bound to the host and not terminating.
  pods: number;
};

export type Plan =
  | { action: "start"; kind: Rollout["kind"]; reason: string }
  | { action: "wait"; reason: string }
  | { action: "none" };

export const target = (pins: Pins): Rollout["target"] => ({
  image: pins.image,
  bundle: { sha256: pins.hostBundle.sha256, baseId: pins.hostBundle.baseId },
});

const since = (value: string | null | undefined) => {
  const time = Date.parse(value ?? "");
  return Number.isNaN(time) ? undefined : time;
};

// Enrolling or recovering re-images the pod, so it needs positive evidence
// that the host is gone, not just a failed ping: the host itself did not
// answer, and Tailscale's control plane has no connected device for it.
const notGone = ({ observation, tailnet }: HostFacts) => {
  if (observation.reachable) return "The host answers";
  if (!observation.silent)
    return `The host's state is unknown: ${observation.error}`;
  if (!tailnet) return "Tailscale could not be read";
  if (tailnet.connected)
    return "Its tailnet device is connected, so the host is running";
};

export const planHost = (facts: HostFacts, pins: Pins, now: Date): Plan => {
  const { host, observation, pod, tailnet } = facts;
  if (host.metadata.deletionTimestamp) return { action: "none" };

  if (observation.reachable) {
    if (!pod)
      return {
        action: "wait",
        reason: "The pod's image is unknown without RunPod access",
      };
    if (pod.imageName !== pins.image)
      return facts.trainingPods
        ? {
            action: "wait",
            reason:
              "A training job runs on the host; it is re-imaged after the job ends",
          }
        : {
            action: "start",
            kind: "reimage",
            reason: `The pod runs ${pod.imageName ?? "an unknown image"}, not the pinned image`,
          };
    if (observation.hostBundleSha256 !== pins.hostBundle.sha256)
      return {
        action: "start",
        kind: "bundle",
        reason: `The host runs bundle ${observation.hostBundleSha256 || "unknown"}, not the pinned bundle`,
      };
    return { action: "none" };
  }

  const alive = notGone(facts);
  if (alive) return { action: "wait", reason: `Not answering ping. ${alive}` };
  if (!pod) return { action: "wait", reason: "The host is unreachable" };
  if (pod.desiredStatus !== "RUNNING")
    return {
      action: "wait",
      reason: `The pod is ${pod.desiredStatus ?? "in an unknown state"}; starting it is a person's decision`,
    };

  const lastSeen = since(host.status?.observed?.lastSeen);
  const created = since(host.metadata.creationTimestamp) ?? now.getTime();
  const deviceSeen = since(tailnet?.lastSeen);
  if (lastSeen === undefined) {
    if (deviceSeen !== undefined && deviceSeen >= created)
      return {
        action: "wait",
        reason:
          "Its tailnet device has been online since the GpuHost was added",
      };
    return now.getTime() - created >= ENROLL_AFTER_MS
      ? {
          action: "start",
          kind: "enroll",
          reason: "The host has never answered since its GpuHost was added",
        }
      : { action: "wait", reason: "Waiting for a new host to answer" };
  }

  // A network outage leaves the container running. A wiped container started
  // as or after the host went silent, and its tailnet device has not been
  // seen since: a restarted container keeps its identity and rejoins.
  const started = since(pod.lastStartedAt);
  if (
    started !== undefined &&
    started >= lastSeen - RESTART_SLACK_MS &&
    // Control notices a stopped container's device a few seconds late.
    (deviceSeen === undefined || deviceSeen < started + RESTART_SLACK_MS) &&
    now.getTime() - started >= REJOIN_WITHIN_MS
  )
    return {
      action: "start",
      kind: "recover",
      reason: `The container restarted at ${pod.lastStartedAt} and the host has not rejoined`,
    };
  return {
    action: "wait",
    reason: `Unreachable since ${host.status?.observed?.lastSeen}; the container has not been replaced`,
  };
};
