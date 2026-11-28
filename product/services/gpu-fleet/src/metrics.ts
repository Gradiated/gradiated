import { Counter, Gauge, Registry } from "prom-client";

export const createMetrics = () => {
  const registry = new Registry();
  return {
    registry,
    leader: new Gauge({
      name: "gradiated_gpu_fleet_leader",
      help: "1 while this replica leads the GPU fleet operator",
      registers: [registry],
    }),
    hosts: new Gauge({
      name: "gradiated_gpu_fleet_hosts",
      help: "GpuHosts by phase",
      labelNames: ["phase"],
      registers: [registry],
    }),
    degraded: new Gauge({
      name: "gradiated_gpu_fleet_host_degraded",
      help: "1 when a GpuHost is Degraded, labelled with the reason",
      labelNames: ["instance_id", "reason"],
      registers: [registry],
    }),
    reconciled: new Gauge({
      name: "gradiated_gpu_fleet_last_reconcile_timestamp_seconds",
      help: "When the leader last finished a reconcile pass",
      registers: [registry],
    }),
    reconcileErrors: new Counter({
      name: "gradiated_gpu_fleet_reconcile_errors_total",
      help: "Reconcile passes that failed before finishing",
      registers: [registry],
    }),
    serviceChanges: new Counter({
      name: "gradiated_gpu_fleet_service_changes_total",
      help: "Egress Services created, adopted or updated",
      labelNames: ["change"],
      registers: [registry],
    }),
    postgresConfigured: new Gauge({
      name: "gradiated_gpu_fleet_postgres_configured",
      help: "1 when the operator has PostgreSQL credentials",
      registers: [registry],
    }),
    postgresSynced: new Gauge({
      name: "gradiated_gpu_fleet_postgres_last_sync_timestamp_seconds",
      help: "When the instances table last matched the GpuHosts",
      registers: [registry],
    }),
    postgresConflicts: new Gauge({
      name: "gradiated_gpu_fleet_postgres_conflicts",
      help: "GpuHosts whose PostgreSQL row disagrees with Git",
      registers: [registry],
    }),
    postgresChanges: new Counter({
      name: "gradiated_gpu_fleet_postgres_changes_total",
      help: "Instance rows inserted, restored or retired",
      labelNames: ["change"],
      registers: [registry],
    }),
    mode: new Gauge({
      name: "gradiated_gpu_fleet_mode",
      help: "1 for the mode the operator runs in: observe or act",
      labelNames: ["mode"],
      registers: [registry],
    }),
    rolloutStep: new Gauge({
      name: "gradiated_gpu_fleet_rollout_step",
      help: "1 for the step a host's running rollout is in",
      labelNames: ["instance_id", "kind", "step"],
      registers: [registry],
    }),
    rolloutStepSeconds: new Gauge({
      name: "gradiated_gpu_fleet_rollout_step_seconds",
      help: "How long a host's running rollout has been in its step",
      labelNames: ["instance_id"],
      registers: [registry],
    }),
    planned: new Gauge({
      name: "gradiated_gpu_fleet_rollout_planned",
      help: "1 when the operator would start this kind of rollout on a host",
      labelNames: ["instance_id", "kind"],
      registers: [registry],
    }),
    rolloutBlocked: new Gauge({
      name: "gradiated_gpu_fleet_rollout_blocked",
      help: "1 while a host's blocked rollout holds the fleet, waiting for capacity",
      labelNames: ["instance_id"],
      registers: [registry],
    }),
    leaseUntil: new Gauge({
      name: "gradiated_gpu_fleet_lease_until_timestamp_seconds",
      help: "When a leased host is due back in the pool",
      labelNames: ["instance_id", "holder"],
      registers: [registry],
    }),
    hostGpus: new Gauge({
      name: "gradiated_gpu_fleet_host_gpus",
      help: "A host's GPUs, labelled with what the host is doing (one state per host)",
      labelNames: ["instance_id", "gpu_product", "state"],
      registers: [registry],
    }),
    workloadGpus: new Gauge({
      name: "gradiated_gpu_fleet_host_workload_gpus",
      help: "GPUs a host's running pods request, by workload (a model pool's name, or training)",
      labelNames: ["instance_id", "workload", "kind"],
      registers: [registry],
    }),
    leaseStarted: new Gauge({
      name: "gradiated_gpu_fleet_lease_started_timestamp_seconds",
      help: "When a leased host was handed to its holder",
      labelNames: ["instance_id", "holder", "purpose", "preemptible"],
      registers: [registry],
    }),
    leaseEvents: new Counter({
      name: "gradiated_gpu_fleet_lease_events_total",
      help: "Lease outcomes: granted, failed, released, expired, preempted or return_failed",
      labelNames: ["event"],
      registers: [registry],
    }),
    keyRevocationFailures: new Counter({
      name: "gradiated_gpu_fleet_key_revocation_failures_total",
      help: "Single-use Tailscale keys the operator could not revoke",
      registers: [registry],
    }),
    rolloutErrors: new Counter({
      name: "gradiated_gpu_fleet_rollout_errors_total",
      help: "Rollout passes that failed before finishing",
      registers: [registry],
    }),
    gradDemand: new Gauge({
      name: "gradiated_gpu_fleet_grad_demand_jobs",
      help: "grad's open train jobs (claimable plus running), one GPU each",
      registers: [registry],
    }),
    gradGpus: new Gauge({
      name: "gradiated_gpu_fleet_grad_gpus",
      help: "GPUs on hosts leased to grad: leasing, leased or returning",
      labelNames: ["state"],
      registers: [registry],
    }),
    gradEvents: new Counter({
      name: "gradiated_gpu_fleet_grad_events_total",
      help: "grad tenancy events: requested, reclaimed, released, trainers_started, trainer_start_failed, token_revoke_failed",
      labelNames: ["event"],
      registers: [registry],
    }),
    // The names below are the ones gpu-controller exported before the
    // rollout moved here, so existing alerts and dashboards keep working.
    rolloutFailed: new Gauge({
      name: "gradiated_gpu_host_update_failed",
      help: "1 while a host's failed rollout holds the fleet",
      labelNames: ["instance_id"],
      registers: [registry],
    }),
    lastSeen: new Gauge({
      name: "gradiated_gpu_host_last_seen_seconds",
      help: "When the host agent last answered ping, or 0 if never",
      labelNames: ["instance_id"],
      registers: [registry],
    }),
    bundleInfo: new Gauge({
      name: "gradiated_gpu_host_bundle_info",
      help: "The host bundle a host runs",
      labelNames: ["instance_id", "sha256", "previous_sha256"],
      registers: [registry],
    }),
    bundleDrift: new Gauge({
      name: "gradiated_gpu_host_bundle_drift",
      help: "1 when a host runs a bundle other than the pin",
      labelNames: ["instance_id"],
      registers: [registry],
    }),
  };
};

export type Metrics = ReturnType<typeof createMetrics>;
