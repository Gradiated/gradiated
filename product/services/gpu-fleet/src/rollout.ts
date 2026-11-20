import { isDeepStrictEqual } from "node:util";

import type { Cluster, ClusterPod } from "./cluster.js";
import { ReimageNotSent, type Enrollment } from "./enroll.js";
import {
  GPU_HOSTS,
  hostName,
  hostState,
  isRunPod,
  LEASE_ANNOTATION,
  leaseEnded,
  leaseRequest,
  parseHosts,
  providerInstanceId,
  RETRY_ANNOTATION,
  type GpuHost,
  type HostLease,
  type Rollout,
} from "./hosts.js";
import type { Kubernetes } from "./kubernetes.js";
import type { Metrics } from "./metrics.js";
import type { Observation } from "./observe.js";
import type { Pins } from "./pins.js";
import {
  leaseRefusal,
  planHost,
  target,
  type HostFacts,
  type Plan,
} from "./plan.js";
import { placementFits, POD_NAMESPACE, type PlacedPod } from "./placement.js";

// What a pass knows of a host: the planner's facts and its GPU use.
type Facts = HostFacts & {
  usedGpus: number;
  servingWorkloads: ClusterPod[];
  residentWorkloads: ClusterPod[];
};

const MINUTE = 60_000;

// How a finished return ended its lease: the holder handed the host back, or
// the operator took it at the lease's end or for a model with nowhere to run.
export const returnEvent = (rollout: Rollout) => {
  if (!rollout.lease) return "released";
  return Date.parse(rollout.lease.until) <= Date.parse(rollout.startedAt)
    ? "expired"
    : "preempted";
};
// The taint Kubernetes adds to a cordoned node.
const UNSCHEDULABLE_TAINT = "node.kubernetes.io/unschedulable";

export const DEFAULT_LIMITS = {
  Cordon: 10 * MINUTE,
  // DeepSeek can take up to 90 minutes to load.
  Surge: 100 * MINUTE,
  Drain: 15 * MINUTE,
  Reimage: 25 * MINUTE,
  Join: 30 * MINUTE,
  Enroll: 45 * MINUTE,
  Promote: 10 * MINUTE,
  Verify: 20 * MINUTE,
  BundleVerify: 35 * MINUTE,
  Soak: 30 * MINUTE,
  Uncordon: 10 * MINUTE,
  Hold: 10 * MINUTE,
  // Apply waits for serving pods still loading, as Surge does.
  Apply: 100 * MINUTE,
  soakFor: 5 * MINUTE,
  unschedulable: 10 * MINUTE,
  // A re-image request RunPod has not acted on by then is sent again.
  reimageAfter: 10 * MINUTE,
  // gradiated-host enroll gets 30 minutes over SSH; another replica waits this out.
  enrollRun: 31 * MINUTE,
  // The first retry of a blocked rollout waits this long, and each later one
  // twice as long as the last, up to blockedMax.
  blockedFor: 5 * MINUTE,
  blockedMax: 60 * MINUTE,
};

export type Limits = typeof DEFAULT_LIMITS;

// Opting in permits retiring a replica without relocating it. Keep local-only
// models out of this set so re-imaging preserves their serving capacity.
export const RETIRE_ON_REIMAGE: ReadonlySet<string> = new Set();

export type RolloutDependencies = {
  api: Kubernetes;
  cluster: Cluster;
  ping: (instanceId: string) => Promise<Observation>;
  pins: () => Promise<Pins>;
  // Undefined while RunPod and Tailscale access is unavailable; asked again each pass.
  enrollment: () => Promise<Enrollment | undefined>;
  modelStatuses: () => Promise<
    ReadonlyMap<string, "available" | "unavailable" | "retired">
  >;
  // observe: in-place bundle updates run, nothing that drains or re-images does.
  mode: "observe" | "act";
  leading: () => boolean;
  // This replica, recorded on enrollments it runs.
  identity: string;
  log: (event: Record<string, unknown>) => void;
  metrics: Metrics;
  now?: () => Date;
  limits?: Partial<Limits>;
  retireOnReimage?: ReadonlySet<string>;
};

export class LeadershipLost extends Error {}
class Fatal extends Error {}

type Outcome =
  | { next: string; set?: Partial<Rollout> }
  | { stay: string; set?: Partial<Rollout> }
  | { done: true; set?: Partial<Rollout>; lease?: HostLease | null }
  | { block: string };

type Step = (
  facts: Facts,
  rollout: Rollout,
  record: (set: Partial<Rollout>) => Promise<Rollout>,
) => Promise<Outcome>;

const FIRST_STEP: Record<Rollout["kind"], string> = {
  enroll: "Cordon",
  recover: "Cordon",
  reimage: "Cordon",
  bundle: "Apply",
  lease: "Cordon",
  return: "Cordon",
};

// Restoring capacity comes first; then the host with the fewest serving pods,
// so the spare host is updated, and proves the image, before any other.
const ORDER: Record<Rollout["kind"], number> = {
  recover: 0,
  return: 0,
  enroll: 1,
  lease: 1,
  reimage: 2,
  bundle: 2,
};

// A lease moves the host's replicas elsewhere first, as a re-image does.
const moves = (kind: Rollout["kind"]) => kind === "reimage" || kind === "lease";

const since = (value: string | null | undefined) => {
  const time = Date.parse(value ?? "");
  return Number.isNaN(time) ? undefined : time;
};

export const createRollouts = (deps: RolloutDependencies) => {
  const limits = { ...DEFAULT_LIMITS, ...deps.limits };
  const now = deps.now ?? (() => new Date());
  const { cluster, metrics } = deps;
  const retired = deps.retireOnReimage ?? RETIRE_ON_REIMAGE;
  // The replicas a surge entry waits for elsewhere: a retired model keeps
  // its count less the replicas on this host; a moved model keeps all of them.
  const kept = ({ replicas, extra }: { replicas: number; extra: number }) =>
    extra < 0 ? replicas + extra : replicas;
  let enrollment: Enrollment | undefined;
  let currentFacts: Facts[] = [];

  const ensureLeading = () => {
    if (!deps.leading()) throw new LeadershipLost("The lease was lost");
  };
  // Every side effect checks the lease first.
  const act = <T>(effect: () => Promise<T>) => {
    ensureLeading();
    return effect();
  };
  const required = () => {
    if (!enrollment)
      throw new Error("RunPod and Tailscale access is unavailable");
    return enrollment;
  };

  // The resourceVersion makes each write conditional, so a replica that read
  // stale status cannot overwrite a newer leader's progress.
  const writeStatus = async (
    host: GpuHost,
    status: {
      rollout?: Rollout | null;
      plan?: string | null;
      lease?: HostLease | null;
    },
  ) => {
    ensureLeading();
    // A merge patch keeps keys it does not name, so dropped keys are nulled.
    const previous = host.status?.rollout ?? {};
    const rollout =
      status.rollout === undefined || status.rollout === null
        ? status.rollout
        : Object.fromEntries(
            [
              ...new Set([
                ...Object.keys(previous),
                ...Object.keys(status.rollout),
              ]),
            ].map((key) => [
              key,
              (status.rollout as Record<string, unknown>)[key] ?? null,
            ]),
          );
    const written = (await deps.api.mergePatch(
      `${GPU_HOSTS}/${host.metadata.name}/status`,
      {
        metadata: { resourceVersion: host.metadata.resourceVersion },
        status: {
          ...(rollout !== undefined && { rollout }),
          ...(status.plan !== undefined && { plan: status.plan }),
          ...(status.lease !== undefined && { lease: status.lease }),
        },
      },
    )) as GpuHost | undefined;
    host.metadata.resourceVersion = written?.metadata?.resourceVersion;
    host.status = written?.status ?? host.status;
  };

  // Removes a lease request that has had its outcome, recorded on the
  // rollout, so the host is planned as any other again. The resourceVersion
  // keeps a request written since the host was read; a failed removal is
  // retried on the next pass.
  const endRequest = async (host: GpuHost) => {
    try {
      const written = (await act(() =>
        deps.api.mergePatch(`${GPU_HOSTS}/${host.metadata.name}`, {
          metadata: {
            resourceVersion: host.metadata.resourceVersion,
            annotations: { [LEASE_ANNOTATION]: null },
          },
        }),
      )) as GpuHost | undefined;
      host.metadata = written?.metadata ?? host.metadata;
    } catch (error) {
      if (error instanceof LeadershipLost) throw error;
      deps.log({
        event: "gpu_lease_request_removal_failed",
        instance_id: host.spec.instanceId,
        error: (error as Error).message,
      });
    }
  };

  const facts = async (host: GpuHost): Promise<Facts> => {
    const id = host.spec.instanceId;
    const quietly = <T>(read: Promise<T> | undefined, source: string) =>
      read?.catch((error: unknown) => {
        deps.log({
          event: "gpu_rollout_read_failed",
          source,
          instance_id: id,
          error: (error as Error).message,
        });
        return undefined;
      });
    const [observation, pod, tailnet, pods, node] = await Promise.all([
      deps.ping(id),
      // Only RunPod hosts have a pod; an AWS host is observed without one.
      quietly(isRunPod(host) ? enrollment?.pod(host) : undefined, "runpod"),
      quietly(enrollment?.tailnetOf(host), "tailscale"),
      cluster.podsOn(id),
      cluster.node(id),
    ]);
    const live = pods.filter((item) => !item.terminating);
    return {
      host,
      observation,
      ...(pod && { pod }),
      ...(tailnet && { tailnet }),
      ...(node && { node }),
      servingPods: live.filter((item) => item.model).length,
      trainingPods: live.filter((item) => item.training).length,
      pods: live.length,
      usedGpus: live.reduce((sum, item) => sum + item.gpus, 0),
      servingWorkloads: live.filter((item) => item.model),
      residentWorkloads: pods,
    };
  };

  // Whether a blocked host's serving pods would fit on the other Ready,
  // schedulable hosts with the same GPU product, largest first. Autoscaling
  // that only fills GPUs never makes a blocked host try again.
  const relocationGap = (blocked: Facts, all: Facts[]) => {
    const { gpuProduct } = blocked.host.spec.inventory;
    const residents: PlacedPod[] = all.flatMap((other) =>
      other.residentWorkloads.map((pod) => ({
        ...pod,
        node: other.node ?? {},
      })),
    );
    const free = all
      .filter(
        (other) =>
          other.host.spec.instanceId !== blocked.host.spec.instanceId &&
          other.node?.ready &&
          !other.node.unschedulable &&
          other.host.spec.inventory.gpuProduct === gpuProduct,
      )
      .map((other) => ({
        node: other.node!,
        gpus: other.host.spec.inventory.gpuCount - other.usedGpus,
      }));
    let attempts = 4096;
    let exhausted = false;
    let missingModel = blocked.servingWorkloads[0]?.model;
    const assign = (remaining: ClusterPod[]): boolean => {
      if (!remaining.length) return true;
      if (--attempts < 0 || remaining.length > 256) {
        exhausted = true;
        return false;
      }

      const choices = remaining
        .map((pod, index) => ({
          pod,
          index,
          destinations: free.filter(
            (other) =>
              other.gpus >= pod.gpus &&
              placementFits(pod.placement, other.node, {
                labels: pod.labels ?? {},
                namespace: pod.namespace ?? POD_NAMESPACE,
                residents,
              }),
          ),
        }))
        .sort(
          (a, b) =>
            a.destinations.length - b.destinations.length ||
            b.pod.gpus - a.pod.gpus,
        );
      const { pod, index, destinations } = choices[0]!;
      missingModel = pod.model;
      for (const destination of destinations) {
        destination.gpus -= pod.gpus;
        residents.push({ ...pod, node: destination.node });
        const fits = assign(
          remaining.filter((_, position) => position !== index),
        );
        residents.pop();
        destination.gpus += pod.gpus;
        if (fits) return true;
        if (exhausted) return false;
      }
      return false;
    };
    // A retired model needs no room, but every replica it keeps on other
    // hosts must be Ready and qualified (as Surge requires), and it must keep
    // at least one, or the host could never proceed.
    for (const model of new Set(
      blocked.servingWorkloads
        .map((pod) => pod.model)
        .filter((model): model is string => !!model && retired.has(model)),
    )) {
      const elsewhere = all
        .filter(
          (other) =>
            other.host.spec.instanceId !== blocked.host.spec.instanceId,
        )
        .flatMap((other) => other.residentWorkloads)
        .filter((pod) => pod.model === model && !pod.terminating);
      const qualified = elsewhere.filter(
        (pod) => pod.ready && pod.qualifiedRuntime !== undefined,
      ).length;
      if (!elsewhere.length)
        return `Retiring this host's ${model} replicas would leave none`;
      if (qualified < elsewhere.length)
        return `Every other ${model} replica must be Ready before retiring this host's`;
    }
    if (
      assign(
        blocked.servingWorkloads.filter(
          (pod) => !pod.model || !retired.has(pod.model),
        ),
      )
    )
      return undefined;

    return exhausted
      ? "Relocation capacity search limit reached; existing replicas preserved"
      : `No capacity for a replacement ${missingModel} replica`;
  };

  const roomFor = (blocked: Facts, all: Facts[]) =>
    relocationGap(blocked, all) === undefined;

  const retryAfter = (rollout: Rollout) =>
    Math.min(
      limits.blockedFor * 2 ** ((rollout.blockedCount ?? 1) - 1),
      limits.blockedMax,
    );

  const readyElsewhere = (pods: ClusterPod[], host: GpuHost) =>
    pods.filter(
      (pod) =>
        pod.ready &&
        pod.qualifiedRuntime !== undefined &&
        !pod.terminating &&
        pod.node !== hostName(host.spec.instanceId),
    ).length;

  const revokeKey = async (host: GpuHost, id: string) => {
    try {
      await required().revoke(id);
    } catch (error) {
      // An unrevoked single-use key still expires within the hour.
      metrics.keyRevocationFailures.inc();
      deps.log({
        event: "gpu_rollout_key_revocation_failed",
        instance_id: host.spec.instanceId,
        key_id: id,
        error: (error as Error).message,
      });
    }
  };
  const revokeKeys = async (host: GpuHost, rollout: Rollout) => {
    for (const id of rollout.keys ?? []) await revokeKey(host, id);
  };

  const imageRuns = ({ pod }: HostFacts, rollout: Rollout) =>
    pod?.imageName === rollout.target.image;

  const healthy = (facts: HostFacts, rollout: Rollout) =>
    facts.observation.reachable &&
    facts.observation.instanceId === facts.host.spec.instanceId &&
    facts.observation.hostBundleSha256 === rollout.target.bundle.sha256 &&
    !facts.observation.trial &&
    (rollout.kind === "bundle" ||
      ((facts.node?.ready ?? false) && imageRuns(facts, rollout)));

  // An update that restarted, moved or requalified a serving pod is broken; one
  // only briefly not Ready, as while the host agent restarts, is waited for.
  const baselineState = async (host: GpuHost, rollout: Rollout) => {
    const pods = await cluster.podsOn(host.spec.instanceId);
    const baseline = Object.entries(rollout.baseline ?? {}).map(
      ([uid, runtime]) => ({
        pod: pods.find((item) => item.uid === uid),
        runtime,
      }),
    );
    if (
      baseline.some(
        ({ pod, runtime }) =>
          !pod || pod.terminating || pod.qualifiedRuntime !== runtime,
      )
    )
      return "broken";

    return baseline.every(({ pod }) => pod?.ready) ? "ready" : "unready";
  };

  const runningTraining = async (host: GpuHost, rollout: Rollout) =>
    (await cluster.podsOn(host.spec.instanceId)).some(
      (pod) =>
        pod.training &&
        !pod.terminating &&
        // A host being recovered runs nothing; only a live host's job counts.
        (moves(rollout.kind) || rollout.kind === "return" || pod.ready),
    );

  const steps: Record<string, Step> = {
    // A pod can be bound while the node is being cordoned, so the next step
    // is decided from the pods on the node once nothing more can land there.
    Cordon: async (facts, rollout) => {
      const { host } = facts;
      if (await runningTraining(host, rollout))
        return { block: "A training job runs on the host" };

      if (rollout.kind === "lease") {
        // Another cordon may guard work Kubernetes cannot see, such as a
        // qualification slot; a lease is only exclusive under its own.
        if (!facts.node) return { block: "The host has no Kubernetes node" };
        if (facts.node.unschedulable && !facts.node.cordonedByRollout)
          return { block: "The node is cordoned by someone else" };
      }
      if (moves(rollout.kind)) {
        const gap = relocationGap(facts, currentFacts);
        if (gap) return { block: gap };
      }

      await act(() => cluster.cordon(host.spec.instanceId));
      if (await runningTraining(host, rollout))
        return { block: "A training job runs on the host" };

      const serving = (await cluster.podsOn(host.spec.instanceId)).some(
        (pod) => pod.model && !pod.terminating,
      );
      if (moves(rollout.kind) && serving) return { next: "Surge" };
      return { next: rollout.kind === "lease" ? "Hold" : "Reimage" };
    },

    // Replacements start elsewhere before anything on this host is removed,
    // so no model drops below its replica count. Each model's count before
    // the surge is recorded before KEDA is told to raise it.
    Surge: async ({ host }, rollout) => {
      if (await runningTraining(host, rollout))
        return { block: "A training job runs on the host" };

      const counts = new Map<string, number>();
      for (const pod of await cluster.podsOn(host.spec.instanceId))
        if (pod.model && !pod.terminating)
          counts.set(pod.model, (counts.get(pod.model) ?? 0) + 1);
      const surge = [...(rollout.surge ?? [])];
      const added = [...counts].filter(
        ([model]) => !surge.some((entry) => entry.model === model),
      );
      if (added.length) {
        for (const [model, count] of added)
          surge.push({
            model,
            replicas: await cluster.replicas(model),
            extra: retired.has(model) ? -count : count,
          });
        return { stay: "Recording each model's replica count", set: { surge } };
      }

      // A retired model scales down only while the replicas it keeps are
      // Ready elsewhere, and only after its pods here are marked to go first.
      for (const entry of surge) {
        if (entry.extra >= 0) continue;
        if (kept(entry) < 1)
          return {
            block: `Retiring this host's ${entry.model} replicas would leave none`,
          };
        const scaled = await cluster.modelPods(entry.model);
        if (readyElsewhere(scaled, host) < kept(entry))
          return {
            stay: `Waiting for another Ready ${entry.model} replica before retiring this one`,
          };
        for (const pod of await cluster.podsOn(host.spec.instanceId))
          if (pod.model === entry.model && !pod.terminating)
            await act(() => cluster.removeFirst(pod));
      }
      for (const { model, replicas, extra } of surge)
        await act(() => cluster.pauseScaling(model, replicas + extra));
      for (const entry of surge) {
        const { model, extra } = entry;
        const replicas = kept(entry);
        const modelPods = await cluster.modelPods(model);
        const stuck = modelPods.find(
          (pod) =>
            pod.unschedulableSince !== undefined &&
            now().getTime() - Date.parse(pod.unschedulableSince || "0") >=
              limits.unschedulable,
        );
        if (stuck && extra >= 0)
          return { block: `No capacity for a replacement ${model} replica` };
        if (readyElsewhere(modelPods, host) < replicas)
          return {
            stay: `Waiting for replacement ${model} replicas to be Ready`,
          };
      }
      return { next: "Drain" };
    },

    Drain: async ({ host }, rollout) => {
      const surge = rollout.surge ?? [];
      for (const entry of surge)
        if (
          readyElsewhere(await cluster.modelPods(entry.model), host) <
          kept(entry)
        )
          return {
            stay: `Replacement ${entry.model} replicas are not all Ready`,
          };

      const remaining = (await cluster.podsOn(host.spec.instanceId)).filter(
        (pod) => pod.model,
      );
      for (const pod of remaining)
        if (!pod.terminating) await act(() => cluster.removeFirst(pod));
      for (const entry of surge)
        await act(() => cluster.pauseScaling(entry.model, kept(entry)));
      if (remaining.length)
        return { stay: `Removing ${remaining.length} pods from the host` };

      for (const { model } of surge)
        await act(() => cluster.pauseScaling(model, null));
      return {
        next: rollout.kind === "lease" ? "Hold" : "Reimage",
        set: { surge: undefined },
      };
    },

    // The drained host stays cordoned and out of the pool until it is returned.
    Hold: async ({ host, node }, rollout) => {
      if (!node?.cordonedByRollout)
        return { block: "The lease does not hold the node's cordon" };
      const left = (await cluster.podsOn(host.spec.instanceId)).filter(
        (pod) => !pod.terminating,
      );
      if (left.some((pod) => pod.model)) return { next: "Surge" };
      if (left.length)
        return { block: "A pod that is not a model replica runs on the host" };

      const request = rollout.lease!;
      // A drain that outlasted the lease never hands the host over.
      if (now().getTime() >= Date.parse(request.until))
        return {
          block: `The lease ended at ${request.until} before the host was drained`,
        };
      return {
        done: true,
        lease: {
          holder: request.holder,
          purpose: request.purpose,
          since: now().toISOString(),
        },
      };
    },

    // The request and its key are recorded before RunPod is asked, so a
    // restart never sends a second re-image or leaves a key unrevoked.
    Reimage: async (facts, rollout, record) => {
      const { host } = facts;
      const enroll = required();

      // A container started on the target image after the request means the
      // re-image happened, even if recording it did not. A re-image to another
      // image shows that image as soon as RunPod accepts it, and the container
      // starts once the image is pulled, which can take longer than
      // reimageAfter. Otherwise a request is sent again only after
      // reimageAfter.
      const requested = since(rollout.reimageRequestedAt);
      if (requested !== undefined) {
        const started = since(facts.pod?.lastStartedAt);
        if (
          imageRuns(facts, rollout) &&
          started !== undefined &&
          started >= requested
        )
          return { next: "Join" };
        // Runpod can wipe a running container without advancing startedAt.
        // A bootstrap device created after our request independently proves the wipe.
        if (imageRuns(facts, rollout)) {
          const bootstrap = await enroll.peer(host);
          const joined = since(bootstrap?.createdAt);
          if (joined !== undefined && joined >= requested)
            return { next: "Join" };
        }
        if (rollout.kind === "reimage" && imageRuns(facts, rollout))
          return {
            stay: "Waiting for RunPod to pull the image and start the pod",
          };
        if (now().getTime() - requested < limits.reimageAfter)
          return { stay: "Waiting for RunPod to restart the pod" };
      }
      // A pod whose binding was in flight during the cordon can still land;
      // nothing on a live host is wiped without being moved or blocking.
      if (await runningTraining(host, rollout))
        return { block: "A training job runs on the host" };
      const live = (await cluster.podsOn(host.spec.instanceId)).filter(
        (pod) => !pod.terminating,
      );
      const serving = live.some((pod) => pod.model);
      if (serving && rollout.kind === "reimage") return { next: "Surge" };
      // A leased host was handed over empty; any pod on it now landed while
      // its cordon was lifted, and is not wiped with it.
      if (serving && rollout.kind === "return")
        return { block: "A model pod runs on the leased host" };
      if (live.length && rollout.kind === "return")
        return { block: "A pod runs on the leased host" };

      if (rollout.kind === "recover" || rollout.kind === "enroll") {
        // The plan saw no connected device; check again right before the wipe.
        const tailnet = await enroll.tailnetOf(host);
        if (tailnet.connected || facts.observation.reachable)
          return { block: "The host is online again, so it is not re-imaged" };
      }

      const key = await act(() => enroll.bootstrapKey(host));
      let current: Rollout;
      try {
        current = await record({
          reimageRequestedAt: now().toISOString(),
          keys: [...(rollout.keys ?? []), key.id],
        });
      } catch (error) {
        await revokeKey(host, key.id);
        throw error;
      }
      try {
        await act(() => enroll.reimage(host, rollout.target.image, key.key));
      } catch (error) {
        // If RunPod may have applied it, the pod may boot with this key, so
        // the request and key stand and the checks above decide what follows.
        if (error instanceof ReimageNotSent) {
          await revokeKey(host, key.id);
          await record({ reimageRequestedAt: undefined }).catch(
            () => undefined,
          );
        }
        throw error;
      }
      return { next: "Join", set: { keys: current.keys } };
    },

    Join: async ({ host }) => {
      const peer = await required().peer(host);
      return peer
        ? { next: "Enroll", set: { bootstrapAddress: peer.ip } }
        : {
            stay: `Waiting for gpu-bootstrap-${providerInstanceId(host)} to join the tailnet`,
          };
    },

    Enroll: async ({ host, observation }, rollout, record) => {
      const enroll = required();
      const peer = await enroll.peer(host);
      // Enrollment may have finished, and the pod promoted, before its status
      // was written; Promote then finds the device created since then.
      if (!peer)
        return rollout.enrolledAt ||
          (observation.reachable &&
            observation.instanceId === host.spec.instanceId)
          ? {
              next: "Promote",
              set: {
                enrolledAt:
                  rollout.enrolledAt ??
                  rollout.enrollStartedAt ??
                  rollout.reimageRequestedAt ??
                  rollout.startedAt,
                bundle: rollout.target.bundle,
              },
            }
          : { stay: "The bootstrap device is not online" };

      const started = since(rollout.enrollStartedAt);
      if (
        started !== undefined &&
        rollout.enrollBy !== deps.identity &&
        now().getTime() - started < limits.enrollRun
      )
        return {
          stay: `An enrollment started by ${rollout.enrollBy} may still be running`,
        };

      const key = await act(() => enroll.inferenceKey(host));
      let current: Rollout;
      try {
        current = await record({
          enrollStartedAt: now().toISOString(),
          enrollBy: deps.identity,
          bootstrapAddress: peer.ip,
          keys: [...(rollout.keys ?? []), key.id],
        });
      } catch (error) {
        await revokeKey(host, key.id);
        throw error;
      }
      let promotion: boolean;
      try {
        promotion = (
          await act(() =>
            enroll.enroll(host, peer, rollout.target.bundle, key.key),
          )
        ).promotion;
      } catch (error) {
        await revokeKey(host, key.id);
        throw error;
      }
      const enrolled = {
        enrolledAt: now().toISOString(),
        bundle: rollout.target.bundle,
      };
      if (promotion) return { next: "Promote", set: enrolled };

      await revokeKeys(host, current);
      return { next: "Verify", set: { ...enrolled, keys: undefined } };
    },

    Promote: async ({ host }, rollout) => {
      const promoted = await required().promoted(
        host,
        rollout.bootstrapAddress ?? "",
        new Date(rollout.enrolledAt ?? 0),
      );
      if ("waiting" in promoted) return { stay: promoted.waiting };

      await revokeKeys(host, rollout);
      return {
        next: "Verify",
        set: { keys: undefined, bundle: rollout.target.bundle },
      };
    },

    Verify: async (facts, rollout) => {
      const { observation } = facts;
      if (rollout.kind === "bundle") {
        if (!observation.reachable) return { stay: "The host is unreachable" };

        const digest = rollout.target.bundle.sha256;
        if (
          [
            observation.failedHostBundleSha256,
            observation.stagingFailedHostBundleSha256,
          ].includes(digest)
        )
          throw new Fatal(`The host rejected or rolled back bundle ${digest}`);
        const baseline = await baselineState(facts.host, rollout);
        if (baseline === "broken")
          throw new Fatal(
            "A serving pod restarted or left the host during the bundle update",
          );
        if (baseline === "unready")
          return { stay: "Waiting for the serving pods to be Ready again" };
      }
      return healthy(facts, rollout)
        ? { next: "Soak" }
        : {
            stay:
              rollout.kind === "bundle"
                ? "Waiting for the host to run the bundle"
                : "Waiting for the host to run the pinned image and bundle with its node Ready",
          };
    },

    Soak: async (facts, rollout) => {
      const baseline =
        rollout.kind === "bundle"
          ? await baselineState(facts.host, rollout)
          : "ready";
      if (baseline === "broken")
        throw new Fatal(
          "A serving pod restarted or left the host during the bundle update",
        );
      // A serving pod that stops being Ready restarts the soak.
      if (baseline === "unready" || !healthy(facts, rollout))
        return {
          stay: "The host is not healthy",
          set: { healthySince: undefined },
        };

      const healthySince = rollout.healthySince ?? now().toISOString();
      if (now().getTime() - Date.parse(healthySince) < limits.soakFor)
        return { stay: "Soaking", set: { healthySince } };
      return rollout.kind === "bundle" ? { done: true } : { next: "Uncordon" };
    },

    Uncordon: async ({ host }) => {
      await act(() => cluster.uncordon(host.spec.instanceId));
      return { done: true };
    },

    Apply: async ({ host }, rollout) => {
      const livePods = async () =>
        (await cluster.podsOn(host.spec.instanceId)).filter(
          (pod) => pod.model && !pod.terminating,
        );
      let pods = await livePods();
      const needsCatalog = pods.some(
        (pod) => !pod.ready && !pod.qualificationFailed && pod.modelId,
      );
      const statuses = needsCatalog ? await deps.modelStatuses() : undefined;
      if (needsCatalog) pods = await livePods();

      const serving = pods.filter(
        (pod) =>
          pod.ready ||
          (!pod.qualificationFailed &&
            (!pod.modelId || statuses?.get(pod.modelId) !== "unavailable")),
      );
      if (serving.some((pod) => !pod.ready || !pod.qualifiedRuntime))
        return {
          stay: "Waiting for every serving pod on the host to be Ready",
        };

      const excluded = pods.filter(
        (pod) =>
          !pod.ready &&
          pod.modelId &&
          statuses?.get(pod.modelId) === "unavailable",
      );
      if (excluded.length)
        deps.log({
          event: "gpu_bundle_unavailable_models_excluded",
          instance_id: host.spec.instanceId,
          bundle: rollout.target.bundle.sha256,
          pods: excluded.map((pod) => ({
            uid: pod.uid,
            model_id: pod.modelId,
          })),
        });

      const baseline = Object.fromEntries(
        serving.map((pod) => [pod.uid, pod.qualifiedRuntime!]),
      );
      return {
        next: "Verify",
        set: { baseline, bundle: rollout.target.bundle },
      };
    },
  };

  const deadline = (rollout: Rollout) =>
    rollout.kind === "bundle" && rollout.step === "Verify"
      ? limits.BundleVerify
      : (limits as Record<string, number>)[rollout.step];

  const advance = async (facts: Facts) => {
    const { host } = facts;
    const id = host.spec.instanceId;
    let rollout = host.status!.rollout!;
    const time = now();
    const record = async (set: Partial<Rollout>) => {
      rollout = { ...rollout, ...set };
      await writeStatus(host, { rollout });
      return rollout;
    };

    const finish = async (result: "Failed" | "Blocked", reason: string) => {
      for (const { model } of rollout.surge ?? [])
        await act(() => cluster.pauseScaling(model, null));
      await revokeKeys(host, rollout);
      // A blocked host goes back into service; a failed one stays cordoned,
      // unless it failed to be leased, which never handed it to anyone.
      if (result === "Blocked" || rollout.kind === "lease")
        await act(() => cluster.uncordon(id));
      deps.log({
        event: "gpu_rollout_" + result.toLowerCase(),
        instance_id: id,
        step: rollout.step,
        reason,
      });
      await record({
        result,
        lastError: reason,
        finishedAt: now().toISOString(),
        surge: undefined,
        keys: undefined,
        ...(result === "Blocked" && {
          blockedCount: (rollout.blockedCount ?? 0) + 1,
        }),
      });
      if (rollout.kind === "lease")
        metrics.leaseEvents.inc({ event: "failed" });
      if (rollout.kind === "return" && result === "Failed")
        metrics.leaseEvents.inc({ event: "return_failed" });
      if (rollout.kind === "lease") await endRequest(host);
    };

    const limit = deadline(rollout);
    if (limit && time.getTime() - Date.parse(rollout.stepStartedAt) > limit)
      return finish(
        "Failed",
        `${rollout.step} did not finish within ${Math.round(limit / MINUTE)} minutes${rollout.lastError ? `: ${rollout.lastError}` : ""}`,
      );

    let outcome: Outcome;
    try {
      outcome = await steps[rollout.step]!(facts, rollout, record);
    } catch (error) {
      if (error instanceof LeadershipLost) throw error;
      if (error instanceof Fatal) return finish("Failed", error.message);

      // Provider and API errors are retried until the step's deadline.
      const message = (error as Error).message;
      if (message !== rollout.lastError) await record({ lastError: message });
      return;
    }

    // A blocked return fails instead, so a host that was not wiped stays
    // cordoned. A blocked lease fails too: it is not retried, and the host
    // goes back into the pool.
    if ("block" in outcome)
      return finish(
        rollout.kind === "return" || rollout.kind === "lease"
          ? "Failed"
          : "Blocked",
        outcome.block,
      );
    const set = outcome.set ?? {};
    if ("stay" in outcome) {
      if (
        Object.entries(set).some(
          ([key, value]) =>
            !isDeepStrictEqual(
              value,
              (rollout as Record<string, unknown>)[key],
            ),
        )
      )
        await record(set);
      return;
    }
    if ("done" in outcome) {
      await revokeKeys(host, rollout);
      deps.log({
        event: "gpu_rollout_succeeded",
        instance_id: id,
        kind: rollout.kind,
      });
      rollout = {
        ...rollout,
        ...set,
        result: "Succeeded",
        finishedAt: now().toISOString(),
        lastError: undefined,
        healthySince: undefined,
        keys: undefined,
      };
      await writeStatus(host, {
        rollout,
        plan: null,
        ...(outcome.lease !== undefined && { lease: outcome.lease }),
        ...(rollout.kind === "return" && { lease: null }),
      });
      if (rollout.kind === "lease")
        metrics.leaseEvents.inc({ event: "granted" });
      if (rollout.kind === "return")
        metrics.leaseEvents.inc({ event: returnEvent(rollout) });
      // An expired or preempted lease's request is done with.
      if (rollout.kind === "return" && rollout.lease) await endRequest(host);
      return;
    }
    deps.log({
      event: "gpu_rollout_step",
      instance_id: id,
      from: rollout.step,
      to: outcome.next,
    });
    await record({
      ...set,
      step: outcome.next,
      stepStartedAt: now().toISOString(),
      lastError: undefined,
      healthySince: undefined,
    });
  };

  const start = async (
    item: Facts,
    plan: Extract<Plan, { action: "start" }>,
    pins: Pins,
    cannot?: string,
  ) => {
    const { host } = item;
    const time = now().toISOString();
    const retry = host.metadata.annotations?.[RETRY_ANNOTATION];
    const parsed = leaseRequest(host);
    const request = parsed && !("invalid" in parsed) ? parsed : undefined;
    // A lease records its request; a return records the one it ends, when it
    // ends the holder's own lease by expiry or preemption.
    const ends =
      plan.kind === "lease" ||
      (plan.kind === "return" &&
        request?.holder === host.status?.lease?.holder);
    // A refused lease fails before it touches the host.
    const refused =
      plan.kind === "lease" ? (cannot ?? leaseRefusal(item, now())) : undefined;
    deps.log({
      event: refused ? "gpu_rollout_failed" : "gpu_rollout_started",
      instance_id: host.spec.instanceId,
      kind: plan.kind,
      reason: refused ? `Not leased: ${refused}` : plan.reason,
    });
    await writeStatus(host, {
      rollout: {
        kind: plan.kind,
        target: target(pins),
        step: FIRST_STEP[plan.kind],
        result: "Running",
        startedAt: time,
        stepStartedAt: time,
        ...(retry && { retry }),
        // The controller keeps applying the bundle the host already runs.
        ...(host.status?.rollout?.bundle && {
          bundle: host.status.rollout.bundle,
        }),
        ...(ends && request && { lease: request }),
        // A retry after a block keeps its count, so the waits keep growing.
        ...(host.status?.rollout?.result === "Blocked" &&
          sameTarget(host.status.rollout, pins) && {
            blockedCount: host.status.rollout.blockedCount,
          }),
        ...(refused && {
          result: "Failed",
          lastError: `Not leased: ${refused}`,
          finishedAt: time,
        }),
      },
      plan: refused ? null : plan.reason,
    });
    if (refused) {
      metrics.leaseEvents.inc({ event: "failed" });
      await endRequest(host);
    }
  };

  // The API server reorders a stored target's fields, so compare values.
  const sameTarget = (rollout: Rollout | undefined, pins: Pins) =>
    rollout !== undefined && isDeepStrictEqual(rollout.target, target(pins));

  // A failed rollout stops the fleet until the pins change or a person sets
  // the retry annotation to a new value. A failed lease never took the host
  // out of the pool, so it stops nothing.
  const holding = (host: GpuHost, pins: Pins) => {
    const rollout = host.status?.rollout;
    if (
      rollout?.result !== "Failed" ||
      rollout.kind === "lease" ||
      !sameTarget(rollout, pins)
    )
      return false;

    const retry = host.metadata.annotations?.[RETRY_ANNOTATION];
    return !retry || retry === rollout.retry;
  };

  const mayAct = (kind: Rollout["kind"]) =>
    deps.mode === "act" || kind === "bundle";

  // Recovering, enrolling or returning a host adds capacity, and a lease
  // fails at once if its replicas have no room, so none of them waits behind
  // a rollout that is waiting for capacity.
  const skipsCapacityWait = (kind: Rollout["kind"]) =>
    kind === "recover" ||
    kind === "enroll" ||
    kind === "return" ||
    kind === "lease";

  // A preemptible lease gives its host back once a model replica that fits
  // there has found no host for `unschedulable`, counted from the last
  // rollout to finish, whose surge replicas may still be leaving. The lease
  // due back soonest goes first.
  const preempt = async (all: Facts[], plans: Map<string, Plan>) => {
    const leased = all.filter((item) => {
      const request = leaseRequest(item.host);
      return (
        item.host.status?.lease &&
        item.node &&
        plans.get(item.host.spec.instanceId)?.action === "wait" &&
        request &&
        !("invalid" in request) &&
        request.preemptible !== false
      );
    });
    if (!leased.length) return;

    const time = now().getTime();
    const settled = Math.max(
      0,
      ...all.map((item) => since(item.host.status?.rollout?.finishedAt) ?? 0),
    );
    const residents: PlacedPod[] = all.flatMap((other) =>
      other.residentWorkloads.map((pod) => ({
        ...pod,
        node: other.node ?? {},
      })),
    );
    const until = (item: Facts) =>
      Date.parse((leaseRequest(item.host) as { until: string }).until);
    leased.sort((a, b) => until(a) - until(b));
    for (const pod of await cluster.unscheduledModelPods()) {
      const pending = since(pod.unschedulableSince);
      if (
        pod.terminating ||
        pending === undefined ||
        time - Math.max(pending, settled) < limits.unschedulable
      )
        continue;
      const host = leased.find(
        ({ host, node }) =>
          pod.gpus <= host.spec.inventory.gpuCount &&
          placementFits(
            pod.placement,
            // The lease's cordon goes with the return.
            {
              ...node!,
              taints: (node!.taints ?? []).filter(
                (taint) => taint.key !== UNSCHEDULABLE_TAINT,
              ),
            },
            {
              labels: pod.labels ?? {},
              namespace: pod.namespace ?? POD_NAMESPACE,
              residents,
            },
          ),
      );
      if (host) {
        plans.set(host.host.spec.instanceId, {
          action: "start",
          kind: "return",
          reason: `Preempted: a ${pod.model} replica has had no host for ${Math.round((time - Math.max(pending, settled)) / MINUTE)} minutes`,
        });
        return;
      }
    }
  };

  const report = (
    all: Facts[],
    pins: Pins,
    plans: Map<string, Plan>,
    blocked?: Facts,
  ) => {
    for (const gauge of [
      metrics.rolloutStep,
      metrics.rolloutStepSeconds,
      metrics.rolloutFailed,
      metrics.rolloutBlocked,
      metrics.planned,
      metrics.lastSeen,
      metrics.bundleInfo,
      metrics.bundleDrift,
      metrics.leaseUntil,
      metrics.leaseStarted,
      metrics.hostGpus,
      metrics.workloadGpus,
    ])
      gauge.reset();
    for (const { host, node, observation, residentWorkloads } of all) {
      const id = host.spec.instanceId;
      const rollout = host.status?.rollout;
      const lease = host.status?.lease;
      const request = leaseRequest(host);
      metrics.hostGpus.set(
        {
          instance_id: id,
          gpu_product: host.spec.inventory.gpuProduct,
          state: hostState(host, node),
        },
        host.spec.inventory.gpuCount,
      );
      const workloads = new Map<string, { kind: string; gpus: number }>();
      // A terminating pod holds its GPUs until it exits, which for a model
      // replica can take its whole grace period.
      for (const pod of residentWorkloads) {
        if (!pod.gpus) continue;
        const kind = pod.model
          ? "serving"
          : pod.training
            ? "training"
            : "other";
        const name = pod.model ?? kind;
        const entry = workloads.get(name) ?? { kind, gpus: 0 };
        workloads.set(name, { kind, gpus: entry.gpus + pod.gpus });
      }
      for (const [workload, { kind, gpus }] of workloads)
        metrics.workloadGpus.set({ instance_id: id, workload, kind }, gpus);
      if (lease)
        metrics.leaseStarted.set(
          {
            instance_id: id,
            holder: lease.holder,
            // Free text a person wrote; long enough to say what the host is for.
            purpose: lease.purpose.slice(0, 120),
            preemptible: String(
              request && "until" in request ? request.preemptible : true,
            ),
          },
          Date.parse(lease.since) / 1000,
        );
      // A handed-back host is due back when its return starts; until then
      // it waits in the queue, which the gauge reports as now.
      if (lease)
        metrics.leaseUntil.set(
          { instance_id: id, holder: lease.holder },
          (request && "until" in request
            ? Date.parse(request.until)
            : rollout?.kind === "return"
              ? Date.parse(rollout.startedAt)
              : now().getTime()) / 1000,
        );
      if (rollout?.result === "Running") {
        metrics.rolloutStep.set(
          { instance_id: id, kind: rollout.kind, step: rollout.step },
          1,
        );
        metrics.rolloutStepSeconds.set(
          { instance_id: id },
          (now().getTime() - Date.parse(rollout.stepStartedAt)) / 1000,
        );
      }
      metrics.rolloutFailed.set(
        { instance_id: id },
        holding(host, pins) ? 1 : 0,
      );
      metrics.rolloutBlocked.set(
        { instance_id: id },
        blocked?.host === host ? 1 : 0,
      );
      const plan = plans.get(id);
      if (plan?.action === "start")
        metrics.planned.set({ instance_id: id, kind: plan.kind }, 1);
      // A host never seen reports 0, so its stale-telemetry alert still fires.
      metrics.lastSeen.set(
        { instance_id: id },
        observation.reachable
          ? now().getTime() / 1000
          : (Date.parse(host.status?.observed?.lastSeen ?? "") || 0) / 1000,
      );
      if (observation.reachable) {
        metrics.bundleInfo.set(
          {
            instance_id: id,
            sha256: observation.hostBundleSha256,
            previous_sha256: observation.previousHostBundleSha256,
          },
          1,
        );
        metrics.bundleDrift.set(
          { instance_id: id },
          observation.hostBundleSha256 === pins.hostBundle.sha256 ? 0 : 1,
        );
      }
    }
  };

  const text = (plan: Plan, held?: string) =>
    plan.action === "none"
      ? undefined
      : plan.action === "wait"
        ? `Waiting: ${plan.reason}`
        : held
          ? `Held: ${held} (${plan.reason})`
          : mayAct(plan.kind)
            ? `Starting ${plan.kind}: ${plan.reason}`
            : `Would ${plan.kind}: ${plan.reason}`;

  const pass = async () => {
    const pins = await deps.pins();
    enrollment = await deps.enrollment().catch((error: unknown) => {
      deps.log({
        event: "gpu_rollout_access_unavailable",
        error: (error as Error).message,
      });
      return undefined;
    });
    const { hosts } = parseHosts(await deps.api.list(GPU_HOSTS));
    const all = await Promise.all(hosts.map(facts));
    currentFacts = all;
    const time = now().getTime();

    // A blocked rollout keeps the fleet waiting for its host, so the order
    // (spare first) holds. It is retried once its pods would fit elsewhere,
    // and each retry waits twice as long as the last.
    let blocked: Facts | undefined;
    let retryBlocked = false;
    const plans = new Map<string, Plan>();
    for (const item of all) {
      const rollout = item.host.status?.rollout;
      const plan =
        rollout?.result === "Running"
          ? ({ action: "none" } as const)
          : planHost(item, pins, now());
      if (
        rollout?.result === "Blocked" &&
        sameTarget(rollout, pins) &&
        plan.action === "start" &&
        // A lease request on the host is refused at once instead.
        plan.kind !== "lease"
      ) {
        blocked = item;
        const room = roomFor(item, all);
        const due = (since(rollout.finishedAt) ?? 0) + retryAfter(rollout);
        retryBlocked = room && time >= due;
        plans.set(
          item.host.spec.instanceId,
          retryBlocked
            ? plan
            : {
                action: "wait",
                reason: `Blocked: ${rollout.lastError}; ${
                  room
                    ? `retried at ${new Date(due).toISOString()}`
                    : "retried once its pods fit on other hosts"
                }`,
              },
        );
      } else plans.set(item.host.spec.instanceId, plan);
    }
    report(all, pins, plans, blocked);
    for (const item of all)
      if (leaseEnded(item.host)) await endRequest(item.host);
    // A leased host stays cordoned even if someone lifts the cordon or its
    // node is recreated, until its return reaches Uncordon.
    for (const item of all) {
      const rollout = item.host.status?.rollout;
      if (
        item.host.status?.lease &&
        !(rollout?.result === "Running" && rollout.step === "Uncordon") &&
        item.node &&
        !item.node.unschedulable
      ) {
        deps.log({
          event: "gpu_lease_recordoned",
          level: "warn",
          instance_id: item.host.spec.instanceId,
          pods: item.pods,
        });
        await act(() => cluster.cordon(item.host.spec.instanceId));
      }
    }

    const running = all
      .filter((item) => item.host.status?.rollout?.result === "Running")
      .sort((a, b) =>
        a.host.status!.rollout!.startedAt.localeCompare(
          b.host.status!.rollout!.startedAt,
        ),
      );
    if (running.length) {
      const first = running[0]!;
      if (mayAct(first.host.status!.rollout!.kind)) return advance(first);

      const paused = "Paused: observe mode does not drain or re-image hosts";
      if (first.host.status?.plan !== paused)
        await writeStatus(first.host, { plan: paused });
      return;
    }
    await preempt(all, plans);

    const halted = all.find((item) => holding(item.host, pins));
    // A new retry annotation restarts that host's rollout; the rest wait for it.
    const retried = all.find((item) => {
      const rollout = item.host.status?.rollout;
      const retry = item.host.metadata.annotations?.[RETRY_ANNOTATION];
      return (
        rollout?.result === "Failed" &&
        rollout.kind !== "lease" &&
        sameTarget(rollout, pins) &&
        retry !== undefined &&
        retry !== rollout.retry
      );
    });
    const waitingForCapacity = blocked && !retryBlocked;
    const holder = halted
      ? `the rollout on ${halted.host.metadata.name} failed`
      : retried
        ? `${retried.host.metadata.name} is being retried`
        : waitingForCapacity
          ? `waiting for capacity for ${blocked?.host.metadata.name}`
          : undefined;
    for (const item of all) {
      const plan = plans.get(item.host.spec.instanceId)!;
      const own = item === blocked || item === retried;
      const restores =
        waitingForCapacity &&
        plan.action === "start" &&
        skipsCapacityWait(plan.kind);
      const wanted = text(plan, own || restores ? undefined : holder);
      if (wanted !== item.host.status?.plan)
        await writeStatus(item.host, { plan: wanted ?? null });
    }
    if (halted) return;

    // A lease that this operator cannot start is refused at once rather than
    // left waiting ahead of the host's other plans.
    const unable =
      deps.mode !== "act"
        ? "the operator is in observe mode"
        : enrollment === undefined
          ? "RunPod and Tailscale access is unavailable"
          : undefined;
    if (unable)
      for (const item of all) {
        const plan = plans.get(item.host.spec.instanceId)!;
        if (plan.action === "start" && plan.kind === "lease")
          await start(item, plan, pins, unable);
      }

    if (retried) {
      const plan = plans.get(retried.host.spec.instanceId)!;
      if (plan.action === "start" && mayAct(plan.kind))
        return start(retried, plan, pins);
      if (plan.action === "none")
        return writeStatus(retried.host, {
          rollout: {
            ...retried.host.status!.rollout!,
            result: "Succeeded",
            retry: retried.host.metadata.annotations?.[RETRY_ANNOTATION],
            lastError: "Retried with nothing left to do",
            finishedAt: now().toISOString(),
          },
        });
      return;
    }

    const candidates = (blocked && retryBlocked ? [blocked] : all)
      .map((item) => ({ item, plan: plans.get(item.host.spec.instanceId)! }))
      .filter(
        (entry) =>
          !waitingForCapacity ||
          (entry.plan.action === "start" && skipsCapacityWait(entry.plan.kind)),
      )
      .filter(
        (
          entry,
        ): entry is {
          item: Facts;
          plan: Extract<Plan, { action: "start" }>;
        } =>
          entry.plan.action === "start" &&
          mayAct(entry.plan.kind) &&
          (entry.plan.kind === "bundle" || enrollment !== undefined),
      )
      .sort(
        (a, b) =>
          ORDER[a.plan.kind] - ORDER[b.plan.kind] ||
          a.item.servingPods - b.item.servingPods ||
          a.item.host.metadata.name.localeCompare(b.item.host.metadata.name),
      );
    if (candidates[0])
      await start(candidates[0].item, candidates[0].plan, pins);
  };

  return { pass };
};
