import type {
  Ec2Instance,
  InstanceTailnet,
  RunPod,
} from "@gradiated/gpu-hosts";

import type { NodeState } from "./cluster.js";
import {
  isRunPod,
  leaseEnded,
  leaseRequest,
  recordedImage,
  RESERVED_TAINT,
  type GpuHost,
  type Rollout,
} from "./hosts.js";
import type { Observation } from "./observe.js";
import { pinnedImage, type Pins } from "./pins.js";

// A new GpuHost gets this long to answer before it is treated as never enrolled.
export const ENROLL_AFTER_MS = 10 * 60_000;
// A restarted container keeps its tailnet identity and rejoins well within
// this; one that has not by then was wiped.
export const REJOIN_WITHIN_MS = 10 * 60_000;
const RESTART_SLACK_MS = 60_000;

export type HostFacts = {
  host: GpuHost;
  observation: Observation;
  // Undefined when RunPod could not be read, and for an AWS host.
  pod?: RunPod;
  // Undefined when EC2 could not be read, and for a RunPod host.
  instance?: Ec2Instance;
  // Whether the instance's type has instance storage; read only for a lease.
  instanceStorage?: boolean;
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

export const target = (pins: Pins, host: GpuHost): Rollout["target"] => ({
  image: pinnedImage(pins, host),
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

// A leased host is left alone until its lease is handed back, expires or is
// given to someone else; then a return re-images it, wiping everything the
// holder left, before it rejoins. A return, once started, is finished first.
const planLease = (facts: HostFacts, now: Date): Plan | undefined => {
  const { host } = facts;
  const request = leaseRequest(host);
  const lease = host.status?.lease;
  const returning = (reason: string): Plan => ({
    action: "start",
    kind: "return",
    reason,
  });
  if (lease) {
    if (host.status?.rollout?.kind === "return")
      return returning("The return did not finish");
    if (!request || "invalid" in request)
      return returning("The lease was handed back");
    if (request.holder !== lease.holder)
      return returning(
        `The lease was given to ${request.holder}, so the host is wiped first`,
      );
    if (now.getTime() >= Date.parse(request.until))
      return returning(`The lease expired at ${request.until}`);

    return {
      action: "wait",
      reason: `Leased to ${lease.holder} until ${request.until}: ${lease.purpose}${
        facts.pods
          ? `; ${facts.pods} pods were scheduled on it while it was uncordoned`
          : ""
      }`,
    };
  }
  if (!request) return undefined;
  // The rollout pass removes a request that has had its outcome.
  if (leaseEnded(host))
    return { action: "wait", reason: "Removing the ended lease request" };

  // The rollout checks the request before it touches the host; a request it
  // refuses fails at once, as a lease that cannot start does.
  return {
    action: "start",
    kind: "lease",
    reason:
      "invalid" in request
        ? "Checking the lease request"
        : `Leasing to ${request.holder} until ${request.until}: ${request.purpose}`,
  };
};

// Why a lease cannot start on this host, checked before anything is changed.
export const leaseRefusal = (facts: HostFacts, now: Date) => {
  const { host, observation, pod, node } = facts;
  const request = leaseRequest(host);
  if (!request) return "the lease request was removed";
  if ("invalid" in request)
    return `the lease annotation is invalid (${request.invalid})`;
  if (now.getTime() >= Date.parse(request.until))
    return `the lease ended at ${request.until} before it started`;
  if (host.spec.extraTaints?.some((taint) => taint.key === RESERVED_TAINT))
    return "the host is reserved";
  // The rollout is waiting for room for this host's replicas, which a lease
  // would need too.
  if (host.status?.rollout?.result === "Blocked")
    return `its ${host.status.rollout.kind} is blocked: ${host.status.rollout.lastError}`;
  if (!observation.reachable) return "the host does not answer";
  if (!node) return "the host has no Kubernetes node";
  // Someone's cordon may guard work Kubernetes cannot see, and a rollout's
  // left by a failed rollout keeps the host out of service on purpose.
  if (node.unschedulable) return "the node is already cordoned";
  // A lease ends with a re-image, which wipes only what it replaces.
  if (isRunPod(host)) {
    if (!pod) return "RunPod could not be read";
    if (pod.volumeInGb || pod.hasAttachedVolumes)
      return "the pod has a RunPod volume, which a re-image would not wipe";
  } else {
    if (!facts.instance) return "EC2 could not be read";
    if ((facts.instance.blockDevices ?? 1) > 1)
      return "the instance has an EBS volume besides its root, which a re-image would not wipe";
    if (facts.instanceStorage === undefined)
      return "EC2 could not tell whether the instance type has instance storage";
    if (facts.instanceStorage)
      return `the ${facts.instance.instanceType} instance type has an instance store, which a re-image would not wipe`;
  }
};

// The image the host runs: RunPod shows the pod's; for an AWS host it is the
// one the operator recorded.
const runningImage = (facts: HostFacts): Plan | { image: string } => {
  const { host, pod, instance } = facts;
  if (isRunPod(host)) {
    if (!pod)
      return {
        action: "wait",
        reason: "The pod's image is unknown without RunPod access",
      };
    return { image: pod.imageName ?? "" };
  }

  if (!instance)
    return {
      action: "wait",
      reason: "The instance's state is unknown without EC2 access",
    };
  const image = recordedImage(host);
  return image === undefined
    ? {
        action: "wait",
        reason:
          "Recording the pinned image as the one the host was adopted under",
      }
    : { image };
};

// An AWS host keeps its root volume across a restart, so it is wiped only
// when a rollout replaced that volume as or after the host went silent.
const planUnreachableAws = (
  { host, instance, tailnet }: HostFacts,
  now: Date,
): Plan => {
  if (!instance) return { action: "wait", reason: "The host is unreachable" };
  if (instance.state !== "running")
    return {
      action: "wait",
      reason: `The instance is ${instance.state}; starting it is a person's decision`,
    };

  const lastSeen = since(host.status?.observed?.lastSeen);
  if (lastSeen === undefined) return neverAnswered(host, tailnet, now);

  const rollout = host.status?.rollout;
  const replaced = rollout?.rootVolumeTask
    ? since(rollout.reimageRequestedAt)
    : undefined;
  if (
    replaced !== undefined &&
    replaced >= lastSeen - RESTART_SLACK_MS &&
    now.getTime() - replaced >= REJOIN_WITHIN_MS
  )
    return {
      action: "start",
      kind: "recover",
      reason: `Its root volume was replaced at ${rollout!.reimageRequestedAt} and the host has not rejoined`,
    };
  return {
    action: "wait",
    reason: `Unreachable since ${host.status?.observed?.lastSeen}; its root volume was not replaced, so recovering it is a person's job`,
  };
};

const neverAnswered = (
  host: GpuHost,
  tailnet: InstanceTailnet | undefined,
  now: Date,
): Plan => {
  const created = since(host.metadata.creationTimestamp) ?? now.getTime();
  const deviceSeen = since(tailnet?.lastSeen);
  if (deviceSeen !== undefined && deviceSeen >= created)
    return {
      action: "wait",
      reason: "Its tailnet device has been online since the GpuHost was added",
    };
  return now.getTime() - created >= ENROLL_AFTER_MS
    ? {
        action: "start",
        kind: "enroll",
        reason: "The host has never answered since its GpuHost was added",
      }
    : { action: "wait", reason: "Waiting for a new host to answer" };
};

export const planHost = (facts: HostFacts, pins: Pins, now: Date): Plan => {
  const { host, observation, pod, tailnet } = facts;
  if (host.metadata.deletionTimestamp) return { action: "none" };

  const lease = planLease(facts, now);
  if (lease) return lease;

  if (observation.reachable) {
    const running = runningImage(facts);
    if ("action" in running) return running;
    if (running.image !== pinnedImage(pins, host))
      return facts.trainingPods
        ? {
            action: "wait",
            reason:
              "A training job runs on the host; it is re-imaged after the job ends",
          }
        : {
            action: "start",
            kind: "reimage",
            reason: isRunPod(host)
              ? `The pod runs ${running.image || "an unknown image"}, not the pinned image`
              : host.status?.image
                ? `The host was re-imaged onto ${running.image}, not the pinned image`
                : `The host was adopted under ${running.image}, and the pinned image has changed`,
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
  if (!isRunPod(host)) return planUnreachableAws(facts, now);
  if (!pod) return { action: "wait", reason: "The host is unreachable" };
  if (pod.desiredStatus !== "RUNNING")
    return {
      action: "wait",
      reason: `The pod is ${pod.desiredStatus ?? "in an unknown state"}; starting it is a person's decision`,
    };

  const lastSeen = since(host.status?.observed?.lastSeen);
  const deviceSeen = since(tailnet?.lastSeen);
  if (lastSeen === undefined) return neverAnswered(host, tailnet, now);

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
