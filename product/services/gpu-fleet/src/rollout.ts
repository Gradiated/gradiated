import type { Cluster, ClusterPod } from "./cluster.js";
import { ReimageNotSent, type Enrollment } from "./enroll.js";
import {
  GPU_HOSTS,
  hostName,
  parseHosts,
  RETRY_ANNOTATION,
  type GpuHost,
  type Rollout,
} from "./hosts.js";
import type { Kubernetes } from "./kubernetes.js";
import type { Metrics } from "./metrics.js";
import type { Observation } from "./observe.js";
import type { Pins } from "./pins.js";
import { planHost, target, type HostFacts, type Plan } from "./plan.js";

// What a pass knows of a host: the planner's facts and its GPU use.
type Facts = HostFacts & { usedGpus: number; servingGpus: number[] };

const MINUTE = 60_000;

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

export type RolloutDependencies = {
  api: Kubernetes;
  cluster: Cluster;
  ping: (instanceId: string) => Promise<Observation>;
  pins: () => Promise<Pins>;
  // Undefined while RunPod and Tailscale access is unavailable; asked again each pass.
  enrollment: () => Promise<Enrollment | undefined>;
  // observe: in-place bundle updates run, nothing that drains or re-images does.
  mode: "observe" | "act";
  leading: () => boolean;
  // This replica, recorded on enrollments it runs.
  identity: string;
  log: (event: Record<string, unknown>) => void;
  metrics: Metrics;
  now?: () => Date;
  limits?: Partial<Limits>;
};

export class LeadershipLost extends Error {}
class Fatal extends Error {}

type Outcome =
  | { next: string; set?: Partial<Rollout> }
  | { stay: string; set?: Partial<Rollout> }
  | { done: true; set?: Partial<Rollout> }
  | { block: string };

type Step = (
  facts: HostFacts,
  rollout: Rollout,
  record: (set: Partial<Rollout>) => Promise<Rollout>,
) => Promise<Outcome>;

const FIRST_STEP: Record<Rollout["kind"], string> = {
  enroll: "Cordon",
  recover: "Cordon",
  reimage: "Cordon",
  bundle: "Apply",
};

// Restoring capacity comes first; then the host with the fewest serving pods,
// so the spare host is updated, and proves the image, before any other.
const ORDER: Record<Rollout["kind"], number> = {
  recover: 0,
  enroll: 1,
  reimage: 2,
  bundle: 2,
};

const since = (value: string | null | undefined) => {
  const time = Date.parse(value ?? "");
  return Number.isNaN(time) ? undefined : time;
};

export const createRollouts = (deps: RolloutDependencies) => {
  const limits = { ...DEFAULT_LIMITS, ...deps.limits };
  const now = deps.now ?? (() => new Date());
  const { cluster, metrics } = deps;
  let enrollment: Enrollment | undefined;

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
    status: { rollout?: Rollout | null; plan?: string | null },
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
        },
      },
    )) as GpuHost | undefined;
    host.metadata.resourceVersion = written?.metadata?.resourceVersion;
    host.status = written?.status ?? host.status;
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
      quietly(enrollment?.pod(host), "runpod"),
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
      servingGpus: live.filter((item) => item.model).map((item) => item.gpus),
    };
  };

  // Whether a blocked host's serving pods would fit on the other Ready,
  // schedulable hosts with the same GPU product, largest first. Autoscaling
  // that only fills GPUs never makes a blocked host try again.
  const roomFor = (blocked: Facts, all: Facts[]) => {
    const { gpuProduct } = blocked.host.spec.inventory;
    const free = all
      .filter(
        (other) =>
          other !== blocked &&
          other.node?.ready &&
          !other.node.unschedulable &&
          other.host.spec.inventory.gpuProduct === gpuProduct,
      )
      .map((other) => other.host.spec.inventory.gpuCount - other.usedGpus);
    return [...blocked.servingGpus]
      .sort((a, b) => b - a)
      .every((need) => {
        const index = free.findIndex((gpus) => gpus >= need);
        if (index < 0) return false;
        free[index]! -= need;
        return true;
      });
  };

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

  // An in-place update must not restart a serving process: each pod stays on
  // the host, Ready, with the same qualified runtime. A pod that is gone also
  // stops the update, so rescheduling cannot certify the bundle.
  const baselineBroken = async (host: GpuHost, rollout: Rollout) => {
    const pods = await cluster.podsOn(host.spec.instanceId);
    return Object.entries(rollout.baseline ?? {}).some(([uid, runtime]) => {
      const pod = pods.find((item) => item.uid === uid);
      return (
        !pod ||
        pod.terminating ||
        !pod.ready ||
        pod.qualifiedRuntime !== runtime
      );
    });
  };

  const runningTraining = async (host: GpuHost, rollout: Rollout) =>
    (await cluster.podsOn(host.spec.instanceId)).some(
      (pod) =>
        pod.training &&
        !pod.terminating &&
        // A host being recovered runs nothing; only a live host's job counts.
        (rollout.kind === "reimage" || pod.ready),
    );

  const steps: Record<string, Step> = {
    // A pod can be bound while the node is being cordoned, so the next step
    // is decided from the pods on the node once nothing more can land there.
    Cordon: async ({ host }, rollout) => {
      if (await runningTraining(host, rollout))
        return { block: "A training job runs on the host" };

      await act(() => cluster.cordon(host.spec.instanceId));
      if (await runningTraining(host, rollout))
        return { block: "A training job runs on the host" };

      const serving = (await cluster.podsOn(host.spec.instanceId)).some(
        (pod) => pod.model && !pod.terminating,
      );
      return {
        next: rollout.kind === "reimage" && serving ? "Surge" : "Reimage",
      };
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
        for (const [model, extra] of added)
          surge.push({ model, replicas: await cluster.replicas(model), extra });
        return { stay: "Recording each model's replica count", set: { surge } };
      }

      for (const { model, replicas, extra } of surge)
        await act(() => cluster.pauseScaling(model, replicas + extra));
      for (const { model, replicas } of surge) {
        const modelPods = await cluster.modelPods(model);
        const stuck = modelPods.find(
          (pod) =>
            pod.unschedulableSince !== undefined &&
            now().getTime() - Date.parse(pod.unschedulableSince || "0") >=
              limits.unschedulable,
        );
        if (stuck)
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
      for (const { model, replicas } of surge)
        if (readyElsewhere(await cluster.modelPods(model), host) < replicas)
          return { stay: `Replacement ${model} replicas are not all Ready` };

      const remaining = (await cluster.podsOn(host.spec.instanceId)).filter(
        (pod) => pod.model,
      );
      for (const pod of remaining)
        if (!pod.terminating) await act(() => cluster.removeFirst(pod));
      for (const { model, replicas } of surge)
        await act(() => cluster.pauseScaling(model, replicas));
      if (remaining.length)
        return { stay: `Removing ${remaining.length} pods from the host` };

      for (const { model } of surge)
        await act(() => cluster.pauseScaling(model, null));
      return { next: "Reimage", set: { surge: undefined } };
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
      if (
        rollout.kind === "reimage" &&
        (await cluster.podsOn(host.spec.instanceId)).some(
          (pod) => pod.model && !pod.terminating,
        )
      )
        return { next: "Surge" };

      if (rollout.kind !== "reimage") {
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
            stay: `Waiting for gpu-bootstrap-${host.spec.provider.podId} to join the tailnet`,
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
        if (await baselineBroken(facts.host, rollout))
          throw new Fatal(
            "A serving pod restarted or left the host during the bundle update",
          );
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
      if (
        rollout.kind === "bundle" &&
        (await baselineBroken(facts.host, rollout))
      )
        throw new Fatal(
          "A serving pod restarted or left the host during the bundle update",
        );
      if (!healthy(facts, rollout))
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

    // Every serving pod is in the baseline, so each must be Ready with a
    // qualified runtime before the update starts.
    Apply: async ({ host }, rollout) => {
      const serving = (await cluster.podsOn(host.spec.instanceId)).filter(
        (pod) => pod.model && !pod.terminating,
      );
      if (serving.some((pod) => !pod.ready || !pod.qualifiedRuntime))
        return {
          stay: "Waiting for every serving pod on the host to be Ready",
        };

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
      // A blocked host goes back into service; a failed one stays cordoned.
      if (result === "Blocked") await act(() => cluster.uncordon(id));
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

    if ("block" in outcome) return finish("Blocked", outcome.block);
    const set = outcome.set ?? {};
    if ("stay" in outcome) {
      if (
        Object.entries(set).some(
          ([key, value]) =>
            JSON.stringify(value) !==
            JSON.stringify((rollout as Record<string, unknown>)[key]),
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
      return writeStatus(host, { rollout, plan: null });
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
    host: GpuHost,
    plan: Extract<Plan, { action: "start" }>,
    pins: Pins,
  ) => {
    const time = now().toISOString();
    const retry = host.metadata.annotations?.[RETRY_ANNOTATION];
    deps.log({
      event: "gpu_rollout_started",
      instance_id: host.spec.instanceId,
      kind: plan.kind,
      reason: plan.reason,
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
        // A retry after a block keeps its count, so the waits keep growing.
        ...(host.status?.rollout?.result === "Blocked" &&
          sameTarget(host.status.rollout, pins) && {
            blockedCount: host.status.rollout.blockedCount,
          }),
      },
      plan: plan.reason,
    });
  };

  const sameTarget = (rollout: Rollout | undefined, pins: Pins) =>
    rollout !== undefined &&
    JSON.stringify(rollout.target) === JSON.stringify(target(pins));

  // A failed rollout stops the fleet until the pins change or a person sets
  // the retry annotation to a new value.
  const holding = (host: GpuHost, pins: Pins) => {
    const rollout = host.status?.rollout;
    if (rollout?.result !== "Failed" || !sameTarget(rollout, pins))
      return false;

    const retry = host.metadata.annotations?.[RETRY_ANNOTATION];
    return !retry || retry === rollout.retry;
  };

  const mayAct = (kind: Rollout["kind"]) =>
    deps.mode === "act" || kind === "bundle";

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
    ])
      gauge.reset();
    for (const { host, observation } of all) {
      const id = host.spec.instanceId;
      const rollout = host.status?.rollout;
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
        plan.action === "start"
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

    const halted = all.find((item) => holding(item.host, pins));
    // A new retry annotation restarts that host's rollout; the rest wait for it.
    const retried = all.find((item) => {
      const rollout = item.host.status?.rollout;
      const retry = item.host.metadata.annotations?.[RETRY_ANNOTATION];
      return (
        rollout?.result === "Failed" &&
        sameTarget(rollout, pins) &&
        retry !== undefined &&
        retry !== rollout.retry
      );
    });
    // Recovering or enrolling a host adds capacity, so a blocked rollout never
    // holds it up.
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
        (plan.kind === "recover" || plan.kind === "enroll");
      const wanted = text(plan, own || restores ? undefined : holder);
      if (wanted !== item.host.status?.plan)
        await writeStatus(item.host, { plan: wanted ?? null });
    }
    if (halted) return;

    if (retried) {
      const plan = plans.get(retried.host.spec.instanceId)!;
      if (plan.action === "start" && mayAct(plan.kind))
        return start(retried.host, plan, pins);
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
          (entry.plan.action === "start" &&
            (entry.plan.kind === "recover" || entry.plan.kind === "enroll")),
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
      await start(candidates[0].item.host, candidates[0].plan, pins);
  };

  return { pass };
};
