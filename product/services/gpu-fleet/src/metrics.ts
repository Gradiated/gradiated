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
  };
};

export type Metrics = ReturnType<typeof createMetrics>;
