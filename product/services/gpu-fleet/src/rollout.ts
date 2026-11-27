import { isDeepStrictEqual } from "node:util";

import type { Cluster, ClusterPod } from "./cluster.js";
import { ReimageNotSent, type Enrollment } from "./enroll.js";
import {
  GRAD_HOLDER,
  GRAD_LIMITS,
  gradLeaseId,
  heldByGrad,
  type Grad,
} from "./grad.js";
import {
  ENROLL_DURING_RUNPOD_HOLD_ANNOTATION,
  GPU_HOSTS,
  hostName,
  hostState,
  isAws,
  isRunPod,
  LEASE_ANNOTATION,
  leaseEnded,
  leaseRequest,
  parseHosts,
  providerInstanceId,
  recordedImage,
  RESUME_ENROLLMENT_VERIFY_ANNOTATION,
  RETRY_ANNOTATION,
  type GpuHost,
  type HostLease,
  type Rollout,
} from "./hosts.js";
import type { Kubernetes } from "./kubernetes.js";
import type { Metrics } from "./metrics.js";
import type { Observation } from "./observe.js";
import { pinnedImage, type Pins } from "./pins.js";
import {
  leaseRefusal,
  planHost,
  target,
  type HostFacts,
  type Plan,
} from "./plan.js";
import {
  fitsOnceUncordoned,
  placementFits,
  POD_NAMESPACE,
  type PlacedPod,
} from "./placement.js";

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

export const DEFAULT_LIMITS = {
  Cordon: 10 * MINUTE,
  // A grad host's trainers have the drain grace to exit; this only catches
  // a step that cannot move on.
  TrainStop: 10 * MINUTE,
  // DeepSeek can take up to 90 minutes to load.
  Surge: 100 * MINUTE,
  Drain: 15 * MINUTE,
  Reimage: 25 * MINUTE,
  Join: 30 * MINUTE,
  Enroll: 45 * MINUTE,
  Promote: 10 * MINUTE,
  RemoveAccess: 10 * MINUTE,
  Verify: 20 * MINUTE,
  BundleVerify: 35 * MINUTE,
  Soak: 30 * MINUTE,
  Uncordon: 10 * MINUTE,
  // A model drained with a replica unavailable gets it back, loaded, by then.
  Restore: 100 * MINUTE,
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
  // Undefined while RunPod and Tailscale access is unavailable; asked again
  // each pass. AWS hosts are reached through it too.
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
  // grad's tenancy: run after every pass, and stops trainers on return.
  grad?: Grad;
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

// A host switching from serving to training is wiped on the way, as it is on
// the way back: a lease to grad re-images the drained host before Hold hands
// it over. Person leases keep the host as it was.
const wipesOnLease = (rollout: Rollout) =>
  rollout.kind === "lease" && rollout.lease?.holder === GRAD_HOLDER;
const afterDrain = (rollout: Rollout) =>
  rollout.kind === "lease" && !wipesOnLease(rollout) ? "Hold" : "Reimage";

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
      image?: string;
      adoptedUnder?: string;
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
          ...(status.image !== undefined && { image: status.image }),
          ...(status.adoptedUnder !== undefined && {
            adoptedUnder: status.adoptedUnder,
          }),
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

  const workloads = (pods: ClusterPod[]) => {
    const live = pods.filter((pod) => !pod.terminating);
    const servingWorkloads = live.filter((pod) => pod.model);

    return {
      servingPods: servingWorkloads.length,
      trainingPods: live.filter((pod) => pod.training).length,
      pods: live.length,
      usedGpus: live.reduce((sum, pod) => sum + pod.gpus, 0),
      servingWorkloads,
      residentWorkloads: pods,
    };
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
    const [observation, pod, instance, tailnet, pods, node] = await Promise.all(
      [
        deps.ping(id),
        quietly(isRunPod(host) ? enrollment?.pod(host) : undefined, "runpod"),
        quietly(isAws(host) ? enrollment?.instance(host) : undefined, "ec2"),
        quietly(enrollment?.tailnetOf(host), "tailscale"),
        cluster.podsOn(id),
        cluster.node(id),
      ],
    );
    const instanceStorage =
      instance && leaseRequest(host)
        ? await quietly(
            enrollment?.instanceStorage(host, instance.instanceType),
            "ec2",
          )
        : undefined;
    return {
      host,
      observation,
      ...(pod && { pod }),
      ...(instance && { instance }),
      ...(instanceStorage !== undefined && { instanceStorage }),
      ...(tailnet && { tailnet }),
      ...(node && { node }),
      ...workloads(pods),
    };
  };

  // Whether a blocked host's serving pods would fit on the other Ready,
  // schedulable hosts with the same GPU product, largest first. Autoscaling
  // that only fills GPUs never makes a blocked host try again.
  const relocationGap = (
    blocked: Facts,
    all: Facts[],
    unavailable: ReadonlySet<string> = new Set(),
  ) => {
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
          (pod) =>
            !pod.model ||
            (!retired.has(pod.model) && !unavailable.has(pod.model)),
        ),
      )
    )
      return undefined;

    return exhausted
      ? "Relocation capacity search limit reached; existing replicas preserved"
      : `No capacity for a replacement ${missingModel} replica`;
  };

  // Why a model on a host with no room for its replica cannot be drained
  // with that replica unavailable, or undefined if it can: its budget allows
  // the disruption, it has one replica here, and every other replica is Ready
  // and qualified, so no other host of the pool is down. Null for a model
  // without a PodDisruptionBudget, which never has a replica unavailable.
  const unavailableRefusal = async (blocked: Facts, model: string) => {
    const allowed = await cluster.disruptionsAllowed(model);
    if (allowed === undefined) return null;
    if (allowed < 1)
      return `the ${model} PodDisruptionBudget allows no disruption`;
    const here = blocked.servingWorkloads.filter((pod) => pod.model === model);
    if (here.length !== 1)
      return `${here.length} ${model} replicas run on the host`;
    if (
      currentFacts.some(
        (other) =>
          other.host !== blocked.host &&
          other.host.status?.rollout?.result === "Running",
      )
    )
      return "another host's rollout is running";
    const replicas = await cluster.replicas(model);
    const ready = readyElsewhere(await cluster.modelPods(model), blocked.host);
    if (ready < 1 || ready < replicas - 1)
      return `not every other ${model} replica is Ready`;
  };

  // A re-image with no room for every replica may drain the fewest models it
  // must with one replica unavailable each, only when each may lose one.
  const relocation = async (
    blocked: Facts,
    all: Facts[],
    kind: Rollout["kind"],
  ): Promise<{ gap?: string; unavailable: string[] }> => {
    const gap = relocationGap(blocked, all);
    if (!gap) return { unavailable: [] };
    if (kind !== "reimage") return { gap, unavailable: [] };

    const models = [
      ...new Set(
        blocked.servingWorkloads
          .map((pod) => pod.model)
          .filter((model): model is string => !!model && !retired.has(model)),
      ),
    ].sort();
    const refusals = new Map<string, string>();
    const eligible: string[] = [];
    for (const model of models) {
      const refusal = await unavailableRefusal(blocked, model);
      if (refusal) refusals.set(model, refusal);
      else if (refusal === undefined) eligible.push(model);
    }

    const subsets = (size: number, from = 0): string[][] =>
      size === 0
        ? [[]]
        : eligible
            .slice(from)
            .flatMap((model, index) =>
              subsets(size - 1, from + index + 1).map((rest) => [
                model,
                ...rest,
              ]),
            );
    for (let size = 1; size <= Math.min(eligible.length, 4); size++)
      for (const subset of subsets(size))
        if (!relocationGap(blocked, all, new Set(subset)))
          return { unavailable: subset };

    const why = [...refusals].map(([, refusal]) => refusal);
    return {
      gap: why.length
        ? `${gap}, and a replica cannot be unavailable: ${why.join("; ")}`
        : gap,
      unavailable: [],
    };
  };

  const roomFor = async (blocked: Facts, all: Facts[], kind: Rollout["kind"]) =>
    (await relocation(blocked, all, kind)).gap === undefined;

  const unavailableText = (models: readonly string[]) =>
    models.map((model) => `one ${model} replica`).join(" and ");

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
  // A token left unrevoked was only ever on the host, which the return
  // wipes, and expires with the lease; so a failure is counted, not waited on.
  const revokeGradTokens = async (host: GpuHost) => {
    const leaseId = gradLeaseId(host);
    if (!leaseId) return;
    const tokens = deps.grad?.tokens;
    try {
      if (!tokens) throw new Error("grad's internal API is not configured");
      const revoked = await act(() => tokens.revoke(leaseId));
      deps.log({
        event: "grad_tokens_revoked",
        instance_id: host.spec.instanceId,
        lease_id: leaseId,
        revoked,
      });
    } catch (error) {
      if (error instanceof LeadershipLost) throw error;
      metrics.gradEvents.inc({ event: "token_revoke_failed" });
      deps.log({
        event: "grad_token_revocation_failed",
        level: "warn",
        instance_id: host.spec.instanceId,
        lease_id: leaseId,
        error: (error as Error).message,
      });
    }
  };
  // A failed re-image leaves no bootstrap access behind if it can help it;
  // what is left is logged, and a retry removes it once the host enrolls.
  // Returns a note on any other instance profile, which is left alone.
  const removeAccess = async (host: GpuHost) => {
    const { left, kept } = await act(() =>
      required().removeBootstrapAccess(host),
    ).catch((error: unknown) => {
      if (error instanceof LeadershipLost) throw error;
      return { left: [(error as Error).message], kept: [] as string[] };
    });
    if (left.length || kept.length)
      deps.log({
        event: "gpu_rollout_bootstrap_access_left",
        instance_id: host.spec.instanceId,
        left,
        kept,
      });
    return kept.length
      ? `; instance profile ${kept.join(", ")} was left in place`
      : "";
  };

  // An AWS host runs the target once this rollout re-imaged and enrolled it.
  const imageRuns = ({ host, pod }: HostFacts, rollout: Rollout) =>
    isRunPod(host)
      ? pod?.imageName === rollout.target.image
      : (rollout.enrolledAt !== undefined &&
          rollout.reimageRequestedAt !== undefined) ||
        recordedImage(host) === rollout.target.image;

  const afterEnroll = (host: GpuHost) =>
    isAws(host) ? "RemoveAccess" : "Verify";

  // A pod whose binding was in flight during the cordon can still land;
  // nothing on a live host is wiped without being moved or blocking.
  const beforeWipe = async (
    facts: Facts,
    rollout: Rollout,
  ): Promise<Outcome | undefined> => {
    const { host } = facts;
    if (await runningTraining(host, rollout))
      return { block: "A training job runs on the host" };
    const live = (await cluster.podsOn(host.spec.instanceId)).filter(
      (pod) => !pod.terminating,
    );
    const serving = live.some((pod) => pod.model);
    if (serving && (rollout.kind === "reimage" || rollout.kind === "lease"))
      return { next: "Surge" };
    if (live.length && rollout.kind === "lease")
      return { block: "A pod that is not a model replica runs on the host" };
    // A leased host was handed over empty; any pod on it now landed while
    // its cordon was lifted, and is not wiped with it.
    if (serving && rollout.kind === "return")
      return { block: "A model pod runs on the leased host" };
    if (live.length && rollout.kind === "return")
      return { block: "A pod runs on the leased host" };

    if (rollout.kind === "enroll" && (live.length || facts.node?.ready))
      return {
        block: "The host already has a Ready node or running workloads",
      };

    if (
      rollout.kind === "enroll" &&
      !facts.observation.reachable &&
      facts.observation.keyMissing &&
      isAws(host) &&
      !facts.instance?.instanceProfileArn
    )
      return {
        block: "EC2 no longer reports an instance profile for the new host",
      };

    if (rollout.kind === "recover" || rollout.kind === "enroll") {
      // The plan saw no connected device; check again right before the wipe.
      const tailnet = await required().tailnetOf(host);
      if (tailnet.connected || facts.observation.reachable)
        return { block: "The host is online again, so it is not re-imaged" };
    }
  };

  // EC2 replaces the root volume in place, keeping the instance and its
  // capacity. The request time, recorded before EC2 is asked, makes the
  // task's client token, so a repeated request is the same task. The key is
  // minted and written only once that task is the last to have succeeded, so
  // only the new root volume's launcher can read it.
  const reimageAws: Step = async (facts, rollout, record) => {
    const { host } = facts;
    const enroll = required();

    if (rollout.rootVolumeTask) {
      const { state } = await enroll.rootVolumeTask(
        host,
        rollout.rootVolumeTask,
      );
      if (state.startsWith("fail"))
        throw new Fatal(
          `Replacing the root volume ${state} (task ${rollout.rootVolumeTask})`,
        );
      if (state !== "succeeded")
        return { stay: "Waiting for EC2 to replace the root volume" };
      const { inFlight, last } = await enroll.replacements(host);
      if (inFlight.length)
        return {
          stay: `Waiting for replace-root-volume task ${inFlight.map((task) => task.id).join(", ")} to end`,
        };
      if (last?.id !== rollout.rootVolumeTask)
        throw new Fatal(
          `Replace-root-volume task ${last?.id} ran after this rollout's, so no bootstrap key was written`,
        );
      const instance = await enroll.instance(host);
      if (instance.state !== "running")
        return {
          stay: `Waiting for the instance, ${instance.state}, to run on its new root volume`,
        };

      await act(() =>
        enroll.attachBootstrapProfile(host, rollout.rootVolumeTask!),
      );
      const key = await act(() => enroll.bootstrapKey(host));
      let current: Rollout;
      try {
        current = await record({ keys: [...(rollout.keys ?? []), key.id] });
      } catch (error) {
        await revokeKey(host, key.id);
        throw error;
      }
      await act(() =>
        enroll.deliverBootstrapKey(
          host,
          rollout.rootVolumeTask!,
          rollout.target.image,
          key.key,
        ),
      );
      return { next: "Join", set: { keys: current.keys } };
    }

    let requestedAt = rollout.reimageRequestedAt;
    if (requestedAt === undefined) {
      const refused = await beforeWipe(facts, rollout);
      if (refused) return refused;

      const refusal = await enroll.ec2Refusal(host);
      if (refusal) throw new Fatal(refusal);
      const instance = await enroll.instance(host);
      if (instance.state === "stopped") {
        await act(() => enroll.startInstance(host));
        return { stay: "Starting the instance" };
      }
      if (instance.state !== "running")
        return { stay: `Waiting for the instance, ${instance.state}, to run` };
      const { inFlight } = await enroll.replacements(host);
      if (inFlight.length)
        return {
          stay: `Waiting for replace-root-volume task ${inFlight.map((task) => task.id).join(", ")} to end`,
        };

      requestedAt = now().toISOString();
      await record({ reimageRequestedAt: requestedAt });
    }

    // A request whose answer was lost is sent again with the same token.
    const { task, imageId } = await act(() =>
      enroll.replaceRoot(host, requestedAt),
    );
    deps.log({
      event: "gpu_rollout_root_volume_replacement",
      instance_id: host.spec.instanceId,
      task_id: task.id,
      image_id: imageId,
    });
    return {
      stay: "Waiting for EC2 to replace the root volume",
      set: { rootVolumeTask: task.id },
    };
  };

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
    // A grad host's return starts here. Its trainers get SIGTERM, save a
    // checkpoint and requeue their jobs; once they exit, or the drain grace
    // is over, the lease's tokens are revoked and the return goes on as any
    // other. A host that does not answer is wiped all the same.
    TrainStop: async ({ host, observation }, rollout) => {
      const grad = deps.grad;
      const elapsed = now().getTime() - Date.parse(rollout.stepStartedAt);
      if (
        grad &&
        observation.reachable &&
        elapsed < grad.drainGraceSeconds * 1000 + GRAD_LIMITS.stopMargin
      ) {
        const status = await grad.trainers.status(host).catch(() => undefined);
        if (status?.workers.some((worker) => worker.state !== "exited")) {
          if (status.workers.some((worker) => worker.state === "running"))
            await act(() =>
              grad.trainers.stop(host, grad.drainGraceSeconds),
            ).catch((error: unknown) => {
              if (error instanceof LeadershipLost) throw error;
              deps.log({
                event: "grad_trainer_stop_failed",
                level: "warn",
                instance_id: host.spec.instanceId,
                error: (error as Error).message,
              });
            });
          return { stay: "Waiting for the trainers to checkpoint and exit" };
        }
      }
      await revokeGradTokens(host);
      return { next: "Cordon" };
    },

    // A pod can be bound while the node is being cordoned, so the next step
    // is decided from the pods on the node once nothing more can land there.
    Cordon: async (facts, rollout) => {
      const { host } = facts;
      // Refused before anything on the host moves.
      if (isAws(host)) {
        const refusal = await required().ec2Refusal(host);
        if (refusal) throw new Fatal(refusal);
      }
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
        const placed = await relocation(facts, currentFacts, rollout.kind);
        if (placed.gap) return { block: placed.gap };
      }

      await act(() => cluster.cordon(host.spec.instanceId));
      if (await runningTraining(host, rollout))
        return { block: "A training job runs on the host" };

      if (moves(rollout.kind)) {
        const here = workloads(await cluster.podsOn(host.spec.instanceId));
        if (here.servingPods) {
          const updated = { ...facts, ...here };
          const all = await Promise.all(
            currentFacts.map(async (item) =>
              item === facts
                ? updated
                : {
                    ...item,
                    ...workloads(
                      await cluster.podsOn(item.host.spec.instanceId),
                    ),
                  },
            ),
          );
          const { gap, unavailable } = await relocation(
            updated,
            all,
            rollout.kind,
          );
          if (gap) return { block: gap };

          if (unavailable.length) {
            deps.log({
              event: "gpu_rollout_replica_unavailable",
              instance_id: host.spec.instanceId,
              models: unavailable,
            });
            await writeStatus(host, {
              plan: `Draining with ${unavailableText(unavailable)} unavailable: no other host has room for it`,
            });
          }

          return {
            next: "Surge",
            set: unavailable.length ? { unavailable } : {},
          };
        }
      }

      return { next: afterDrain(rollout) };
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
      for (const model of rollout.unavailable ?? []) {
        const count = counts.get(model) ?? 0;
        if (count > 1)
          return {
            block: `Cannot drain with one ${model} replica unavailable: ${count} replicas run on the host`,
          };
      }

      const surge = [...(rollout.surge ?? [])];
      const added = [...counts].filter(
        ([model]) => !surge.some((entry) => entry.model === model),
      );
      if (added.length) {
        for (const [model, count] of added)
          surge.push({
            model,
            replicas: await cluster.replicas(model),
            // A model drained unavailable is scaled down by its one
            // replica here, as a retired model is, until Drain unpauses it.
            extra:
              retired.has(model) || rollout.unavailable?.includes(model)
                ? -count
                : count,
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
        next: afterDrain(rollout),
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
      if (!isRunPod(host)) return reimageAws(facts, rollout, record);
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
      const refused = await beforeWipe(facts, rollout);
      if (refused) return refused;

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
      return { next: afterEnroll(host), set: { ...enrolled, keys: undefined } };
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
        next: afterEnroll(host),
        set: { keys: undefined, bundle: rollout.target.bundle },
      };
    },

    // An enrolled AWS host keeps no AWS credentials: its bootstrap secret is
    // deleted and its instance profile removed before it serves again.
    RemoveAccess: async ({ host }, rollout) => {
      const { left, kept } = await act(() =>
        required().removeBootstrapAccess(host),
      );
      if (left.length)
        throw new Error(
          `The host enrolled, but ${left.join(" and ")} could not be removed`,
        );
      // Not the fleet's to remove, but the host must not serve holding it.
      if (kept.length)
        throw new Fatal(
          `The host enrolled, but it has instance profile ${kept.join(", ")}, not the bootstrap profile; it stays cordoned until that profile is removed`,
        );

      if (host.status?.image !== rollout.target.image)
        await writeStatus(host, { image: rollout.target.image });
      return { next: "Verify" };
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
      // A wiped grad host is handed over once it runs the pins; it stays
      // cordoned, so there is nothing to soak.
      return healthy(facts, rollout)
        ? { next: rollout.kind === "lease" ? "Hold" : "Soak" }
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

    Uncordon: async ({ host }, rollout) => {
      await act(() => cluster.uncordon(host.spec.instanceId));
      return rollout.unavailable?.length ? { next: "Restore" } : { done: true };
    },

    // The next host waits until each model drained unavailable has all its
    // replicas Ready and qualified again, so two never go down together.
    Restore: async (_facts, rollout) => {
      for (const model of rollout.unavailable ?? []) {
        const replicas = await cluster.replicas(model);
        const live = (await cluster.modelPods(model)).filter(
          (pod) => !pod.terminating,
        );
        const ready = live.filter(
          (pod) => pod.ready && pod.qualifiedRuntime !== undefined,
        ).length;
        if (ready < replicas || ready < live.length)
          return {
            stay: `Waiting for the ${model} replica drained unavailable to be Ready again`,
          };
      }
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
      const kept =
        isAws(host) && rollout.reimageRequestedAt
          ? await removeAccess(host)
          : "";
      // A blocked host goes back into service; a failed one stays cordoned,
      // unless it failed to be leased, which never handed it to anyone. A
      // grad lease that failed after asking for the wipe may have left the
      // host half re-imaged, so it is held as leased and the return, which
      // fails safe, wipes it again.
      const wiping =
        wipesOnLease(rollout) && rollout.reimageRequestedAt !== undefined;
      if (result === "Blocked" || (rollout.kind === "lease" && !wiping))
        await act(() => cluster.uncordon(id));
      deps.log({
        event: "gpu_rollout_" + result.toLowerCase(),
        instance_id: id,
        step: rollout.step,
        reason,
      });
      await record({
        result,
        lastError: reason + kept,
        finishedAt: now().toISOString(),
        surge: undefined,
        keys: undefined,
        ...(result === "Blocked" && {
          blockedCount: (rollout.blockedCount ?? 0) + 1,
        }),
      });
      if (wiping)
        await writeStatus(host, {
          lease: {
            holder: rollout.lease!.holder,
            purpose: rollout.lease!.purpose,
            since: now().toISOString(),
          },
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
        target: target(pins, host),
        step:
          plan.kind === "return" && heldByGrad(host)
            ? "TrainStop"
            : FIRST_STEP[plan.kind],
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
          sameTarget(host, host.status.rollout, pins) && {
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
  const sameTarget = (
    host: GpuHost,
    rollout: Rollout | undefined,
    pins: Pins,
  ) =>
    rollout !== undefined &&
    isDeepStrictEqual(rollout.target, target(pins, host));

  // A failed rollout stops the fleet until the pins change or a person sets
  // the retry annotation to a new value. A failed lease never took the host
  // out of the pool, so it stops nothing.
  const holding = (host: GpuHost, pins: Pins) => {
    const rollout = host.status?.rollout;
    if (
      rollout?.result !== "Failed" ||
      rollout.kind === "lease" ||
      !sameTarget(host, rollout, pins)
    )
      return false;

    const retry = host.metadata.annotations?.[RETRY_ANNOTATION];
    return !retry || retry === rollout.retry;
  };

  const isRunPodJoinFailure = ({ host }: Facts) =>
    isRunPod(host) &&
    host.status?.rollout?.kind === "recover" &&
    host.status.rollout.step === "Join";

  const resumableEnrollmentVerify = (item: Facts) => {
    const { host, node } = item;
    const rollout = host.status?.rollout;
    const requested =
      host.metadata.annotations?.[RESUME_ENROLLMENT_VERIFY_ANNOTATION];
    const timeout = `Verify did not finish within ${Math.round(limits.Verify / MINUTE)} minutes`;

    if (
      !requested ||
      !isAws(host) ||
      host.metadata.annotations?.[ENROLL_DURING_RUNPOD_HOLD_ANNOTATION] !==
        "true" ||
      host.status?.lease ||
      leaseRequest(host) ||
      item.pods ||
      (node?.unschedulable && !node.cordonedByRollout) ||
      !rollout ||
      rollout.kind !== "enroll" ||
      rollout.step !== "Verify" ||
      rollout.result !== "Failed" ||
      !rollout.enrolledAt ||
      rollout.finishedAt !== requested ||
      rollout.lastError !== timeout ||
      !healthy(item, rollout)
    )
      return;

    return rollout;
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
      const host = leased.find(({ host, node }) =>
        fitsOnceUncordoned(pod, host.spec.inventory.gpuCount, node!, residents),
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

  // grad's tenancy runs after every pass that read the fleet, even one that
  // advanced or waited on a rollout, so a reclaim never queues behind one.
  const pass = async () => {
    let read: Facts[] | undefined;
    try {
      await rolloutPass((all) => (read = all));
    } finally {
      if (deps.grad && read)
        await deps.grad.reconcile(read).catch((error: unknown) => {
          if (error instanceof LeadershipLost) return;
          deps.log({
            event: "grad_pass_failed",
            error: (error as Error).message,
          });
        });
    }
  };

  const rolloutPass = async (onRead: (all: Facts[]) => void) => {
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
    onRead(all);
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
        sameTarget(item.host, rollout, pins) &&
        plan.action === "start" &&
        // A lease request on the host is refused at once instead.
        plan.kind !== "lease"
      ) {
        blocked = item;
        const room = await roomFor(item, all, plan.kind);
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
    // EC2 cannot show what an AWS host the operator never re-imaged runs, so
    // it is taken to be current until the pinned image changes.
    for (const item of all)
      if (
        isAws(item.host) &&
        item.observation.reachable &&
        recordedImage(item.host) === undefined
      ) {
        deps.log({
          event: "gpu_rollout_host_adopted",
          instance_id: item.host.spec.instanceId,
          image: pinnedImage(pins, item.host),
        });
        await writeStatus(item.host, {
          adoptedUnder: pinnedImage(pins, item.host),
        });
      }
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

    const held = all.filter((item) => holding(item.host, pins));
    if (mayAct("enroll")) {
      for (const item of held) {
        if (
          !held.every((other) => other === item || isRunPodJoinFailure(other))
        )
          continue;
        const rollout = resumableEnrollmentVerify(item);
        if (!rollout) continue;

        const { host } = item;
        const id = host.spec.instanceId;
        await act(() => cluster.cordon(id));
        await writeStatus(host, {
          rollout: {
            ...rollout,
            result: "Running",
            stepStartedAt: now().toISOString(),
            finishedAt: undefined,
            lastError: undefined,
            healthySince: undefined,
          },
        });
        deps.log({ event: "gpu_enrollment_verify_resumed", instance_id: id });
        return;
      }
    }

    const halted = held[0];
    // A failed RunPod recovery is still held while explicitly opted-in,
    // empty AWS hosts enroll through their separate bootstrap path.
    const onlyRunPodJoinFailures = held.every(isRunPodJoinFailure);
    const mayEnrollDuringHold = (item: Facts, plan: Plan) =>
      onlyRunPodJoinFailures &&
      plan.action === "start" &&
      plan.kind === "enroll" &&
      isAws(item.host) &&
      !item.pods &&
      !item.node?.ready &&
      !item.host.status?.observed?.lastSeen &&
      recordedImage(item.host) === undefined &&
      item.host.metadata.annotations?.[ENROLL_DURING_RUNPOD_HOLD_ANNOTATION] ===
        "true";

    // A new retry annotation restarts that host's rollout; the rest wait for it.
    const retried = all.find((item) => {
      const rollout = item.host.status?.rollout;
      const retry = item.host.metadata.annotations?.[RETRY_ANNOTATION];
      return (
        rollout?.result === "Failed" &&
        rollout.kind !== "lease" &&
        sameTarget(item.host, rollout, pins) &&
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
      const independentEnrollment = halted && mayEnrollDuringHold(item, plan);
      const wanted = text(
        plan,
        own || restores || independentEnrollment ? undefined : holder,
      );
      if (wanted !== item.host.status?.plan)
        await writeStatus(item.host, { plan: wanted ?? null });
    }
    if (halted) {
      if (enrollment && mayAct("enroll")) {
        for (const item of all) {
          const plan = plans.get(item.host.spec.instanceId)!;
          if (plan.action === "start" && mayEnrollDuringHold(item, plan))
            return start(item, plan, pins);
        }
      }

      return;
    }

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
