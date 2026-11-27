import { readFile } from "node:fs/promises";
import path from "node:path";

import { z } from "zod";

import type { Cluster, ClusterPod, NodeState } from "./cluster.js";
import {
  GPU_HOSTS,
  hostEndpoint,
  hostState,
  LEASE_ANNOTATION,
  leaseRequest,
  type GpuHost,
  type LeaseRequest,
} from "./hosts.js";
import { isConflict, type Kubernetes } from "./kubernetes.js";
import type { Metrics } from "./metrics.js";
import { fitsOnceUncordoned, type PlacedPod } from "./placement.js";

// grad, the training platform, is a preemptible tenant of the fleet. While its
// train queue needs GPUs and serving has room to spare, the operator leases
// idle hosts to this holder, wipes them, and runs the pinned grad-trainer
// bundle on them with a token scoped to the lease. A model replica that needs
// one of those hosts takes it back at once: the trainers checkpoint and
// requeue their jobs, the lease's tokens are revoked, and the host is wiped
// again before it serves.
export const GRAD_HOLDER = "grad";

const MINUTE = 60_000;

export const GRAD_LIMITS = {
  // Demand must go unmet this long before a host is leased, and stay below
  // the leased GPUs this long before one is handed back.
  demandFor: 2 * MINUTE,
  idleFor: 15 * MINUTE,
  // A model replica the scheduler has found no node for takes a grad host
  // after this, counted from the last rollout to finish, whose surge
  // replicas may still be landing. Other preemptible leases wait ten minutes.
  reclaimAfter: 30_000,
  leaseFor: 24 * 60 * MINUTE,
  // grad caps a lease token at seven days.
  tokenFor: 7 * 24 * 60 * MINUTE - MINUTE,
  // TrainStop moves on this long after the drain grace, trainers or not:
  // the re-image ends whatever is left.
  stopMargin: 15_000,
};

// GPU memory per GPU, in GB, by the CRD's inventory.gpuProduct.
export const GPU_MEMORY_GB: Readonly<Record<string, number>> = {
  L4: 24,
  L40S: 48,
  H100: 80,
  "RTX-PRO-6000": 96,
  H200: 141,
  B200: 180,
  B300: 288,
};

// Every catalog base trains on one 80 GB GPU with the recipe defaults, so a
// job whose demand names no memory class needs this much.
export const DEFAULT_MEMORY_CLASS_GB = 80;

const csv = z
  .string()
  .default("")
  .transform((value) =>
    value
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean),
  );

export const gradConfigSchema = z
  .object({
    // Off unless set to true: nothing is leased to grad, and hosts it holds
    // are handed back.
    GRAD_ENABLED: z
      .enum(["true", "false"])
      .default("false")
      .transform((value) => value === "true"),
    // Free serving GPUs that must remain on the other in-pool hosts of the
    // same GPU product after a host is leased to grad.
    GRAD_BUFFER_GPUS: z.coerce.number().int().min(0).default(8),
    GRAD_MAX_HOSTS: z.coerce.number().int().min(0).max(64).default(0),
    // The GPU products (the fleet's pools) whose hosts grad may lease.
    GRAD_GPU_PRODUCTS: csv.pipe(
      z.array(
        z
          .string()
          .refine((product) => product in GPU_MEMORY_GB, "unknown GPU product"),
      ),
    ),
    // How long trainers get to checkpoint and requeue after SIGTERM before
    // the host agent kills them.
    GRAD_DRAIN_GRACE_SECONDS: z.coerce
      .number()
      .int()
      .min(30)
      .max(600)
      .default(90),
    GRAD_PROMETHEUS_URL: z.url().optional(),
    // grad's internal listener, where the operator mints lease tokens.
    GRAD_INTERNAL_URL: z.url().optional(),
    // grad's worker listener, which the trainers poll.
    GRAD_SERVER_URL: z.url().optional(),
    // The orchestrator key for the internal listener (a mounted secret).
    GRAD_ORCHESTRATOR_KEY_FILE: z.string().min(1).optional(),
    // The grad-trainer release's key in runtimes.json.
    GRAD_TRAINER_RUNTIME: z
      .string()
      .regex(/^[0-9a-f]{64}$/)
      .optional(),
  })
  .superRefine((config, context) => {
    if (!config.GRAD_ENABLED) return;
    for (const name of [
      "GRAD_PROMETHEUS_URL",
      "GRAD_INTERNAL_URL",
      "GRAD_SERVER_URL",
      "GRAD_ORCHESTRATOR_KEY_FILE",
      "GRAD_TRAINER_RUNTIME",
    ] as const)
      if (!config[name])
        context.addIssue({
          code: "custom",
          path: [name],
          message: "is required when GRAD_ENABLED is true",
        });
    if (config.GRAD_MAX_HOSTS < 1)
      context.addIssue({
        code: "custom",
        path: ["GRAD_MAX_HOSTS"],
        message: "must be at least 1 when GRAD_ENABLED is true",
      });
    if (!config.GRAD_GPU_PRODUCTS.length)
      context.addIssue({
        code: "custom",
        path: ["GRAD_GPU_PRODUCTS"],
        message: "must name a GPU product when GRAD_ENABLED is true",
      });
  })
  .transform((config) => ({
    enabled: config.GRAD_ENABLED,
    bufferGpus: config.GRAD_BUFFER_GPUS,
    maxHosts: config.GRAD_MAX_HOSTS,
    products: config.GRAD_GPU_PRODUCTS,
    drainGraceSeconds: config.GRAD_DRAIN_GRACE_SECONDS,
    prometheusUrl: config.GRAD_PROMETHEUS_URL,
    internalUrl: config.GRAD_INTERNAL_URL,
    serverUrl: config.GRAD_SERVER_URL,
    orchestratorKeyFile: config.GRAD_ORCHESTRATOR_KEY_FILE,
    trainerRuntime: config.GRAD_TRAINER_RUNTIME,
  }));

export type GradConfig = z.infer<typeof gradConfigSchema>;

export const parseGradConfig = (env: Record<string, string | undefined>) =>
  gradConfigSchema.parse(env);

// Open train jobs by the GPU memory each needs, in GB.
export type Demand = ReadonlyMap<number, number>;

// Every grad-server replica exports the same queue gauge, so take the
// largest. A gpu_memory_gb label, should grad add one, splits it by memory
// class; without it every job needs an 80 GB GPU.
export const DEMAND_QUERY =
  'max by (gpu_memory_gb) (grad_jobs_open{kind="train"})';

const vectorSchema = z.object({
  status: z.literal("success"),
  data: z.object({
    resultType: z.literal("vector"),
    result: z.array(
      z.object({
        metric: z.record(z.string(), z.string()),
        value: z.tuple([z.number(), z.string()]),
      }),
    ),
  }),
});

// grad exports the gauge for every job kind, zero included, so no samples
// means grad or its scrape is down, which is not the same as no demand.
export const prometheusDemand =
  (url: string, query = DEMAND_QUERY, timeout = 10_000) =>
  async (): Promise<Demand> => {
    const response = await fetch(
      `${url.replace(/\/$/, "")}/api/v1/query?query=${encodeURIComponent(query)}`,
      { redirect: "error", signal: AbortSignal.timeout(timeout) },
    );
    if (!response.ok)
      throw new Error(
        `Prometheus answered the demand query with ${response.status}`,
      );
    const { result } = vectorSchema.parse(await response.json()).data;
    if (!result.length) throw new Error("grad_jobs_open has no samples");

    const demand = new Map<number, number>();
    for (const { metric, value } of result) {
      const jobs = Math.ceil(Number(value[1]));
      const memory = Number(metric.gpu_memory_gb ?? DEFAULT_MEMORY_CLASS_GB);
      if (!(jobs > 0) || !(memory > 0)) continue;
      demand.set(memory, (demand.get(memory) ?? 0) + jobs);
    }
    return demand;
  };

const trainerStatusSchema = z.object({
  lease_id: z.string().nullable().default(null),
  // Whether the requested grad-trainer bundle is staged on the host.
  staged: z.boolean().default(false),
  workers: z
    .array(
      z.object({
        gpu: z.string(),
        state: z.enum(["running", "draining", "exited"]),
      }),
    )
    .default([]),
});

export type TrainerStatus = {
  leaseId: string | null;
  staged: boolean;
  workers: { gpu: string; state: "running" | "draining" | "exited" }[];
};

export type TrainerStart = {
  leaseId: string;
  runtime: string;
  serverUrl: string;
  token: string;
};

// The host agent's trainer operations. They carry the host's management key
// and no controller fencing epoch: trainers are not pods, and the agent
// refuses to start them beside a pod or to admit a pod beside them.
export type Trainers = {
  status(host: GpuHost, runtime?: string): Promise<TrainerStatus>;
  start(host: GpuHost, request: TrainerStart): Promise<TrainerStatus>;
  stop(host: GpuHost, graceSeconds: number): Promise<void>;
};

export const hostTrainers = (
  keys: string,
  endpoint: (instanceId: string) => string = hostEndpoint,
  timeout = 15_000,
): Trainers => {
  const call = async (host: GpuHost, body: Record<string, unknown>) => {
    const id = host.spec.instanceId;
    const key = (await readFile(path.join(keys, id), "utf8")).trim();
    const response = await fetch(endpoint(id), {
      method: "POST",
      headers: {
        authorization: `Bearer ${key}`,
        "content-type": "application/json",
      },
      body: JSON.stringify(body),
      redirect: "error",
      signal: AbortSignal.timeout(timeout),
    });
    const answer = (await response.json().catch(() => null)) as {
      error?: unknown;
    } | null;
    if (!response.ok)
      throw new Error(
        `The host agent answered ${String(body.operation)} with ${response.status}${
          typeof answer?.error === "string" ? ` (${answer.error})` : ""
        }`,
      );
    return answer;
  };
  const status = (answer: unknown): TrainerStatus => {
    const parsed = trainerStatusSchema.parse(answer);
    return {
      leaseId: parsed.lease_id,
      staged: parsed.staged,
      workers: parsed.workers,
    };
  };

  return {
    status: async (host, runtime) =>
      status(
        await call(host, {
          operation: "train_status",
          ...(runtime && { runtime }),
        }),
      ),
    // The token travels only in this request, over the tailnet to the
    // host's private agent, never in a pod spec or the GpuHost.
    start: async (host, request) =>
      status(
        await call(host, {
          operation: "train_start",
          lease_id: request.leaseId,
          runtime: request.runtime,
          environment: {
            GRAD_SERVER_URL: request.serverUrl,
            GRAD_WORKER_TOKEN: request.token,
          },
        }),
      ),
    stop: async (host, graceSeconds) => {
      await call(host, {
        operation: "train_stop",
        grace_seconds: graceSeconds,
      });
    },
  };
};

// grad's internal worker-token API (POST/DELETE /internal/v1/worker-tokens).
export type WorkerTokens = {
  mint(input: {
    hostId: string;
    leaseId: string;
    gpuMemoryGb: number;
    expiresAt: Date;
  }): Promise<string>;
  // Revokes every token minted for the lease; returns how many.
  revoke(leaseId: string): Promise<number>;
};

const mintedSchema = z.object({ token: z.string().regex(/^gradwt_\S+$/) });
const revokedSchema = z.object({ revoked: z.number().int().min(0) });

export const gradWorkerTokens = (
  url: string,
  key: () => Promise<string>,
  timeout = 10_000,
): WorkerTokens => {
  const call = async (method: string, route: string, body?: unknown) => {
    const response = await fetch(
      `${url.replace(/\/$/, "")}/internal/v1/worker-tokens${route}`,
      {
        method,
        headers: {
          authorization: `Bearer ${(await key()).trim()}`,
          ...(body !== undefined && { "content-type": "application/json" }),
        },
        ...(body !== undefined && { body: JSON.stringify(body) }),
        redirect: "error",
        signal: AbortSignal.timeout(timeout),
      },
    );
    if (!response.ok)
      throw new Error(
        `grad answered ${method} worker-tokens with ${response.status}`,
      );
    return response.json();
  };

  return {
    mint: async ({ hostId, leaseId, gpuMemoryGb, expiresAt }) =>
      mintedSchema.parse(
        await call("POST", "", {
          host_id: hostId,
          lease_id: leaseId,
          kinds: ["train"],
          gpu_memory_gb: gpuMemoryGb,
          expires_at: expiresAt.toISOString(),
        }),
      ).token,
    revoke: async (leaseId) =>
      revokedSchema.parse(
        await call("DELETE", `/${encodeURIComponent(leaseId)}`),
      ).revoked,
  };
};

// The lease's ID in grad's token registry: the host and when it was handed
// over, so a restarted operator names the same lease and the return revokes
// every token minted for it.
export const gradLeaseId = (host: GpuHost) => {
  const since = Date.parse(host.status?.lease?.since ?? "");
  return Number.isNaN(since) ? undefined : `${host.spec.instanceId}.${since}`;
};

const requestOf = (host: GpuHost) => {
  const request = leaseRequest(host);
  return request && !("invalid" in request) ? request : undefined;
};
const requestedByGrad = (host: GpuHost) =>
  requestOf(host)?.holder === GRAD_HOLDER;
export const heldByGrad = (host: GpuHost) =>
  host.status?.lease?.holder === GRAD_HOLDER;
const gpusOf = (host: GpuHost) => host.spec.inventory.gpuCount;
const memoryOf = (host: GpuHost) =>
  GPU_MEMORY_GB[host.spec.inventory.gpuProduct] ?? 0;
const since = (value: string | undefined) => {
  const time = Date.parse(value ?? "");
  return Number.isNaN(time) ? undefined : time;
};

// The largest memory class whose jobs these hosts' GPUs cannot all run. The
// largest classes are filled first, each from the smallest GPUs with enough
// memory, so one v0 job runs per GPU.
export const unmetDemand = (demand: Demand, hosts: GpuHost[]) => {
  const slots = hosts
    .map((host) => ({ memory: memoryOf(host), gpus: gpusOf(host) }))
    .sort((a, b) => a.memory - b.memory);
  for (const [memoryGb, jobs] of [...demand].sort(([a], [b]) => b - a)) {
    let left = jobs;
    for (const slot of slots) {
      if (slot.memory < memoryGb || !left) continue;
      const used = Math.min(slot.gpus, left);
      slot.gpus -= used;
      left -= used;
    }
    if (left > 0) return { memoryGb, gpus: left };
  }
};

// What the rollout pass read about a host.
export type GradHostFacts = {
  host: GpuHost;
  node?: NodeState;
  observation: { reachable: boolean };
  pods: number;
  usedGpus: number;
  residentWorkloads: ClusterPod[];
};

export type GradDependencies = {
  api: Kubernetes;
  cluster: Pick<Cluster, "unscheduledModelPods">;
  config: GradConfig;
  demand: () => Promise<Demand>;
  trainers: Trainers;
  // Undefined until GRAD_INTERNAL_URL and its key are configured.
  tokens?: WorkerTokens;
  mode: "observe" | "act";
  leading: () => boolean;
  log: (event: Record<string, unknown>) => void;
  metrics: Metrics;
  now?: () => Date;
  limits?: Partial<typeof GRAD_LIMITS>;
};

export const createGrad = (deps: GradDependencies) => {
  const limits = { ...GRAD_LIMITS, ...deps.limits };
  const now = deps.now ?? (() => new Date());
  const { config, metrics } = deps;
  // Kept in memory: a restarted operator waits the windows out again.
  let unmetSince: number | undefined;
  let surplusSince: number | undefined;

  // Writes or removes grad's request on a fresh read of the host, only if
  // the host has no request or has grad's, and only if the host is unchanged
  // since that read: a person's lease is never touched.
  const writeRequest = async (host: GpuHost, request: LeaseRequest | null) => {
    if (!deps.leading()) return false;
    const current = (await deps.api.get(
      `${GPU_HOSTS}/${host.metadata.name}`,
    )) as GpuHost | undefined;
    if (!current) return false;
    const existing = leaseRequest(current);
    if (
      request
        ? existing !== undefined
        : !existing || "invalid" in existing || existing.holder !== GRAD_HOLDER
    )
      return false;
    try {
      await deps.api.mergePatch(`${GPU_HOSTS}/${host.metadata.name}`, {
        metadata: {
          resourceVersion: current.metadata.resourceVersion,
          annotations: {
            [LEASE_ANNOTATION]: request ? JSON.stringify(request) : null,
          },
        },
      });
      return true;
    } catch (error) {
      if (isConflict(error)) return false;
      throw error;
    }
  };

  // Hands a host back: removing the request starts the return, and the
  // trainers start checkpointing now rather than when the return reaches
  // them, which may wait behind another host's rollout.
  const handBack = async (
    item: GradHostFacts,
    reason: string,
    event: "reclaimed" | "released",
  ) => {
    if (!(await writeRequest(item.host, null))) return false;
    deps.log({
      event: `grad_lease_${event}`,
      instance_id: item.host.spec.instanceId,
      reason,
    });
    metrics.gradEvents.inc({ event });
    if (heldByGrad(item.host) && item.observation.reachable)
      await deps.trainers
        .stop(item.host, config.drainGraceSeconds)
        .catch((error: unknown) =>
          deps.log({
            event: "grad_trainer_stop_failed",
            level: "warn",
            instance_id: item.host.spec.instanceId,
            error: (error as Error).message,
          }),
        );
    return true;
  };

  // A leased host runs one trainer per GPU under a fresh token whenever any
  // is missing. A token is minted only once the bundle is staged, so a
  // staging host does not mint one every pass.
  const ensureTrainers = async ({ host, observation }: GradHostFacts) => {
    const leaseId = gradLeaseId(host);
    const request = requestOf(host);
    const { trainerRuntime: runtime, serverUrl } = config;
    if (!leaseId || !request || !observation.reachable) return;
    if (!runtime || !serverUrl || !deps.tokens || !deps.leading()) return;

    const status = await deps.trainers.status(host, runtime);
    const workers = status.leaseId === leaseId ? status.workers : [];
    if (
      workers.filter((worker) => worker.state === "running").length >=
      gpusOf(host)
    )
      return;
    if (workers.some((worker) => worker.state === "draining") || !status.staged)
      return;

    const token = await deps.tokens.mint({
      hostId: host.spec.instanceId,
      leaseId,
      gpuMemoryGb: memoryOf(host),
      expiresAt: new Date(
        Math.min(Date.parse(request.until), now().getTime() + limits.tokenFor),
      ),
    });
    await deps.trainers.start(host, { leaseId, runtime, serverUrl, token });
    metrics.gradEvents.inc({ event: "trainers_started" });
    deps.log({
      event: "grad_trainers_started",
      instance_id: host.spec.instanceId,
      lease_id: leaseId,
    });
  };

  // Free GPUs left for serving on the other in-pool hosts of its product.
  const headroom = (all: GradHostFacts[], candidate: GradHostFacts) =>
    all
      .filter(
        (other) =>
          other !== candidate &&
          other.host.spec.inventory.gpuProduct ===
            candidate.host.spec.inventory.gpuProduct &&
          hostState(other.host, other.node) === "in_pool",
      )
      .reduce(
        (sum, other) => sum + Math.max(0, gpusOf(other.host) - other.usedGpus),
        0,
      );

  // An idle in-pool host of an eligible product, with enough memory, that no
  // pending model replica would take, and whose loss leaves the buffer. The
  // smallest host that covers the shortfall goes first, else the largest.
  const spare = (
    all: GradHostFacts[],
    pending: ClusterPod[],
    residents: PlacedPod[],
    unmet: { memoryGb: number; gpus: number },
  ) =>
    all
      .filter((item) => {
        const { host, node, observation } = item;
        const rollout = host.status?.rollout;
        return (
          config.products.includes(host.spec.inventory.gpuProduct) &&
          memoryOf(host) >= unmet.memoryGb &&
          hostState(host, node) === "in_pool" &&
          !leaseRequest(host) &&
          !host.status?.lease &&
          !item.pods &&
          observation.reachable &&
          node?.ready &&
          !node.unschedulable &&
          rollout?.result !== "Running" &&
          rollout?.result !== "Blocked" &&
          !pending.some((pod) =>
            fitsOnceUncordoned(pod, gpusOf(host), node, residents),
          ) &&
          headroom(all, item) >= config.bufferGpus
        );
      })
      .sort((a, b) => {
        const [x, y] = [gpusOf(a.host), gpusOf(b.host)];
        const [cx, cy] = [x >= unmet.gpus, y >= unmet.gpus];
        return (
          Number(cy) - Number(cx) ||
          (cx ? x - y : y - x) ||
          a.host.metadata.name.localeCompare(b.host.metadata.name)
        );
      })[0];

  const report = (grad: GradHostFacts[], demand?: Demand) => {
    metrics.gradGpus.reset();
    for (const state of ["leasing", "leased", "returning"] as const)
      metrics.gradGpus.set({ state }, 0);
    for (const { host } of grad)
      metrics.gradGpus.inc(
        {
          state: !heldByGrad(host)
            ? "leasing"
            : requestedByGrad(host)
              ? "leased"
              : "returning",
        },
        gpusOf(host),
      );
    if (!demand) return;
    metrics.gradDemand.reset();
    for (const [memory, jobs] of demand)
      metrics.gradDemand.set({ gpu_memory_gb: String(memory) }, jobs);
  };

  // Runs after each rollout pass, whether or not a rollout is under way:
  // reclaiming a host and starting trainers never wait behind another host.
  const reconcile = async (all: GradHostFacts[]) => {
    const time = now().getTime();
    const grad = all.filter(
      (item) => requestedByGrad(item.host) || heldByGrad(item.host),
    );
    // Off and holding nothing, the fleet behaves as it did before grad.
    if (
      deps.mode !== "act" ||
      !deps.leading() ||
      (!config.enabled && !grad.length)
    )
      return report(grad);

    // 1. Inference first. A model replica with no host takes a grad host it
    // fits, unless a host already on its way back will take it.
    const pending = (await deps.cluster.unscheduledModelPods()).filter(
      (pod) => !pod.terminating,
    );
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
    const fits = (pod: ClusterPod, item: GradHostFacts) =>
      item.node !== undefined &&
      fitsOnceUncordoned(pod, gpusOf(item.host), item.node, residents);
    const returning = new Map(
      all
        .filter(({ host }) => {
          const lease = host.status?.lease;
          const rollout = host.status?.rollout;
          return (
            lease &&
            (requestOf(host)?.holder !== lease.holder ||
              (rollout?.kind === "return" && rollout.result === "Running"))
          );
        })
        .map((item) => [item, gpusOf(item.host)]),
    );
    // A host not yet handed over runs no trainers, so it goes first; then the
    // newest lease, which has had the least time to make progress.
    const reclaimable = grad
      .filter((item) => requestedByGrad(item.host))
      .sort(
        (a, b) =>
          Number(heldByGrad(a.host)) - Number(heldByGrad(b.host)) ||
          (since(b.host.status?.lease?.since) ?? 0) -
            (since(a.host.status?.lease?.since) ?? 0),
      );
    const taken = new Set<GradHostFacts>();
    for (const pod of pending) {
      const pendingSince = since(pod.unschedulableSince);
      if (
        pendingSince === undefined ||
        time - Math.max(pendingSince, settled) < limits.reclaimAfter
      )
        continue;
      const back = [...returning].find(
        ([item, gpus]) => gpus >= pod.gpus && fits(pod, item),
      );
      if (back) {
        returning.set(back[0], back[1] - pod.gpus);
        continue;
      }
      const item = reclaimable.find(
        (candidate) => !taken.has(candidate) && fits(pod, candidate),
      );
      if (!item) continue;
      taken.add(item);
      returning.set(item, gpusOf(item.host) - pod.gpus);
      await handBack(
        item,
        `a ${pod.model} replica has had no host for ${Math.round((time - Math.max(pendingSince, settled)) / 1000)} seconds`,
        "reclaimed",
      );
    }

    const kept = grad.filter(
      (item) => requestedByGrad(item.host) && !taken.has(item),
    );
    if (!config.enabled) {
      for (const item of kept)
        await handBack(item, "grad tenancy is disabled", "released");
      return report(grad);
    }

    // 2. Trainers on every host handed over to grad.
    for (const item of kept)
      if (
        heldByGrad(item.host) &&
        item.host.status?.rollout?.result !== "Running"
      )
        await ensureTrainers(item).catch((error: unknown) => {
          metrics.gradEvents.inc({ event: "trainer_start_failed" });
          deps.log({
            event: "grad_trainer_start_failed",
            level: "warn",
            instance_id: item.host.spec.instanceId,
            error: (error as Error).message,
          });
        });

    // 3. Demand. Without it the current leases are held as they are.
    let demand: Demand;
    try {
      demand = await deps.demand();
    } catch (error) {
      unmetSince = surplusSince = undefined;
      deps.log({
        event: "grad_demand_unavailable",
        level: "warn",
        error: (error as Error).message,
      });
      return report(grad);
    }
    report(grad, demand);
    if (taken.size) return;

    const unmet = unmetDemand(
      demand,
      kept.map((item) => item.host),
    );
    if (unmet) {
      surplusSince = undefined;
      unmetSince ??= time;
      // One lease at a time: each re-images a host, and the fleet does one
      // rollout at a time.
      if (
        kept.some((item) => !heldByGrad(item.host)) ||
        kept.length >= config.maxHosts ||
        time - unmetSince < limits.demandFor
      )
        return;
      const item = spare(all, pending, residents, unmet);
      if (!item) return;
      const leased = await writeRequest(item.host, {
        holder: GRAD_HOLDER,
        purpose: `grad training: ${unmet.gpus} open train jobs need GPUs with ${unmet.memoryGb} GB`,
        until: new Date(time + limits.leaseFor).toISOString(),
        preemptible: true,
      });
      if (!leased) return;
      unmetSince = undefined;
      metrics.gradEvents.inc({ event: "requested" });
      deps.log({
        event: "grad_lease_requested",
        instance_id: item.host.spec.instanceId,
        gpus: gpusOf(item.host),
        unmet_gpus: unmet.gpus,
      });
      return;
    }
    unmetSince = undefined;

    // 4. Scale down: the newest handed-over host whose GPUs the open jobs
    // have not needed for idleFor goes back.
    const newest = kept
      .filter((item) => heldByGrad(item.host))
      .sort(
        (a, b) =>
          (since(b.host.status?.lease?.since) ?? 0) -
          (since(a.host.status?.lease?.since) ?? 0),
      )[0];
    if (
      !newest ||
      unmetDemand(
        demand,
        kept.filter((item) => item !== newest).map((item) => item.host),
      )
    ) {
      surplusSince = undefined;
      return;
    }
    surplusSince ??= time;
    if (time - surplusSince < limits.idleFor) return;
    if (
      await handBack(
        newest,
        "grad's open train jobs no longer need its GPUs",
        "released",
      )
    )
      surplusSince = undefined;
  };

  return {
    reconcile,
    trainers: deps.trainers,
    tokens: deps.tokens,
    drainGraceSeconds: config.drainGraceSeconds,
  };
};

export type Grad = ReturnType<typeof createGrad>;
