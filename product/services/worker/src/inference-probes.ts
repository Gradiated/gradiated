import { randomUUID } from "node:crypto";
import type { ModelReplica } from "@gradiated/control";
import { Counter, Gauge, Histogram, type Registry } from "prom-client";
import { sleep } from "./sleep.js";
import { createProbeDeadline } from "./probe-deadline.js";

const labels = ["model", "deployment"] as const;
type Labels = (typeof labels)[number];

export class InferenceProbeMetrics {
  readonly inventory: Gauge;
  private readonly targets: Gauge<Labels>;
  private readonly success: Gauge<Labels>;
  private readonly attempts: Counter<Labels | "result">;
  private readonly latency: Histogram<Labels>;
  private readonly routedTargets: Gauge<"model">;
  private readonly routedSuccess: Gauge<"model">;
  private readonly routedAttempts: Counter<"model" | "result">;
  private readonly routedLatency: Histogram<"model">;
  private readonly models = new Set<string>();
  private readonly active = new Map<
    string,
    { model: string; deployment: string }
  >();

  constructor(registry: Registry) {
    this.inventory = new Gauge({
      name: "gradiated_inference_probe_inventory_timestamp_seconds",
      help: "Latest discovery of serving deployments by the probe leader.",
      registers: [registry],
    });
    this.targets = new Gauge({
      name: "gradiated_inference_probe_target",
      help: "Serving deployment included in public inference probes.",
      labelNames: labels,
      registers: [registry],
    });
    this.success = new Gauge({
      name: "gradiated_inference_probe_last_success_timestamp_seconds",
      help: "Latest completed valid public inference response; zero until first success.",
      labelNames: labels,
      registers: [registry],
    });
    this.attempts = new Counter({
      name: "gradiated_inference_probe_requests_total",
      help: "Public inference probes by model, deployment and outcome.",
      labelNames: [...labels, "result"],
      registers: [registry],
    });
    this.latency = new Histogram({
      name: "gradiated_inference_probe_duration_seconds",
      help: "Public inference probe duration including full response body.",
      labelNames: labels,
      buckets: [0.05, 0.1, 0.25, 0.5, 1, 2, 4],
      registers: [registry],
    });
    this.routedTargets = new Gauge({
      name: "gradiated_inference_routed_probe_target",
      help: "Model included in public inference probes with normal gateway routing.",
      labelNames: ["model"],
      registers: [registry],
    });
    this.routedSuccess = new Gauge({
      name: "gradiated_inference_routed_probe_last_success_timestamp_seconds",
      help: "Latest valid public inference response using normal gateway routing.",
      labelNames: ["model"],
      registers: [registry],
    });
    this.routedAttempts = new Counter({
      name: "gradiated_inference_routed_probe_requests_total",
      help: "Public inference probes using normal gateway routing by model and outcome.",
      labelNames: ["model", "result"],
      registers: [registry],
    });
    this.routedLatency = new Histogram({
      name: "gradiated_inference_routed_probe_duration_seconds",
      help: "Public inference probe duration using normal gateway routing.",
      labelNames: ["model"],
      buckets: [0.05, 0.1, 0.25, 0.5, 1, 2, 4],
      registers: [registry],
    });
  }

  discover(replicas: readonly ModelReplica[]) {
    const models = new Set(replicas.map((replica) => replica.modelId));
    for (const model of this.models) {
      if (models.has(model)) continue;

      this.routedTargets.remove({ model });
      this.routedSuccess.remove({ model });
      this.routedLatency.remove({ model });
      for (const result of ["success", "failure"])
        this.routedAttempts.remove({ model, result });
      this.models.delete(model);
    }
    for (const model of models) {
      if (!this.models.has(model)) this.routedSuccess.set({ model }, 0);
      this.models.add(model);
      this.routedTargets.set({ model }, 1);
    }
    const ids = new Set(replicas.map((replica) => replica.id));
    for (const [id, label] of this.active) {
      if (ids.has(id)) continue;

      this.targets.remove(label);
      this.success.remove(label);
      this.latency.remove(label);
      for (const result of ["success", "failure"])
        this.attempts.remove({ ...label, result });
      this.active.delete(id);
    }
    for (const replica of replicas) {
      const label = { model: replica.modelId, deployment: replica.id };
      if (!this.active.has(replica.id)) this.success.set(label, 0);
      this.active.set(replica.id, label);
      this.targets.set(label, 1);
    }
    this.inventory.set(Date.now() / 1000);
  }

  record(replica: ModelReplica, succeeded: boolean, duration: number) {
    const label = { model: replica.modelId, deployment: replica.id };
    this.attempts.inc({ ...label, result: succeeded ? "success" : "failure" });
    this.latency.observe(label, duration);
    if (succeeded) this.success.set(label, Date.now() / 1000);
  }

  recordRouted(replica: ModelReplica, succeeded: boolean, duration: number) {
    const label = { model: replica.modelId };
    this.routedAttempts.inc({
      ...label,
      result: succeeded ? "success" : "failure",
    });
    this.routedLatency.observe(label, duration);
    if (succeeded) this.routedSuccess.set(label, Date.now() / 1000);
  }
}

export const probeLeaseScript = `
if redis.call('GET', KEYS[1]) == ARGV[1] then
  return redis.call('PEXPIRE', KEYS[1], 15000)
end
if redis.call('SET', KEYS[1], ARGV[1], 'NX', 'PX', 15000) then return 1 end
return 0`;
const releaseLeaseScript = `
if redis.call('GET', KEYS[1]) == ARGV[1] then return redis.call('DEL', KEYS[1]) end
return 0`;

export const runInferenceProbes = async (options: {
  eval: (
    script: string,
    options: { keys: string[]; arguments: string[] },
  ) => Promise<unknown>;
  replicas: () => Promise<readonly ModelReplica[]>;
  probe: (
    replica: ModelReplica,
    signal: AbortSignal,
    scope: "deployment" | "model",
  ) => Promise<void>;
  metrics: InferenceProbeMetrics;
  beforePass?: () => Promise<void>;
  onReady: (durationSeconds: number) => Promise<void>;
  signal: AbortSignal;
}) => {
  const lease = {
    keys: ["gradiated:inference-probes:leader"],
    arguments: [randomUUID()],
  };
  try {
    while (!options.signal.aborted) {
      const start = performance.now();
      // Discovery and both four-second phases must fit inside the fifteen-second lease.
      const deadline = createProbeDeadline(options.signal, 12_000);
      const { signal } = deadline;
      try {
        if (Number(await options.eval(probeLeaseScript, lease)) === 1) {
          signal.throwIfAborted();
          const replicas = await options.replicas();
          signal.throwIfAborted();
          if (replicas.length) await options.beforePass?.();
          signal.throwIfAborted();
          options.metrics.discover(replicas);
          const models = [
            ...new Map(
              replicas.map((replica) => [replica.modelId, replica]),
            ).values(),
          ];
          for (const [scope, targets] of [
            ["model", models],
            ["deployment", replicas],
          ] as const) {
            signal.throwIfAborted();
            await Promise.all(
              targets.map(async (replica) => {
                const request = createProbeDeadline(signal, 4_000);
                const started = performance.now();
                let succeeded = false;
                try {
                  await options.probe(replica, request.signal, scope);
                  succeeded = !request.signal.aborted;
                } catch {
                  // SDK errors can contain authentication headers or response bodies.
                } finally {
                  request.dispose();
                }
                const duration = (performance.now() - started) / 1000;
                if (scope === "model")
                  options.metrics.recordRouted(replica, succeeded, duration);
                else options.metrics.record(replica, succeeded, duration);
              }),
            );
          }
        } else {
          options.metrics.discover([]);
          options.metrics.inventory.set(0);
        }
        await options.onReady((performance.now() - start) / 1000);
      } finally {
        deadline.dispose();
      }
      await sleep(
        Math.max(0, 5_000 - (performance.now() - start)),
        options.signal,
      );
    }
  } finally {
    options.metrics.discover([]);
    options.metrics.inventory.set(0);
    await options.eval(releaseLeaseScript, lease);
  }
};
