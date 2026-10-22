import type { FleetHost, FleetSyncResult } from "@gradiated/control";

import {
  holdUntilDrained,
  releaseIfDrained,
  uncordonIfReturned,
} from "./drain.js";
import {
  GPU_HOSTS,
  parseHosts,
  type GpuHost,
  type HostStatus,
} from "./hosts.js";
import type { Kubernetes } from "./kubernetes.js";
import type { Metrics } from "./metrics.js";
import type { Observation } from "./observe.js";
import { reconcileService } from "./services.js";
import { hostStatus } from "./status.js";

// lastSeen changes on every ping; it is only rewritten this often on its own.
export const LAST_SEEN_REFRESH_MS = 5 * 60_000;

export type SyncFleet = (
  hosts: FleetHost[],
  beforeCommit: () => void,
) => Promise<FleetSyncResult>;

export type FleetDependencies = {
  api: Kubernetes;
  metrics: Metrics;
  ping: (instanceId: string) => Promise<Observation>;
  // Undefined while the operator has no PostgreSQL credential.
  sync: () => SyncFleet | undefined;
  // Checked before every write, so a replica that lost the lease stops writing.
  leading: () => boolean;
  log: (event: Record<string, unknown>) => void;
  now?: () => Date;
};

export class LeadershipLost extends Error {}

const fleetHost = (host: GpuHost): FleetHost => ({
  instanceId: host.spec.instanceId,
  provider: host.spec.provider.name,
  accountId: host.spec.provider.accountId,
  podId: host.spec.provider.podId,
  sku: `${host.spec.inventory.gpuCount}x ${host.spec.inventory.gpuProduct}`,
  ...(host.spec.provider.machineId && {
    faultDomain: `runpod:${host.spec.provider.machineId}`,
  }),
});

// The rollout and plan fields belong to the rollout loop, not this comparison.
const withoutLastSeen = (status: HostStatus | undefined) =>
  JSON.stringify({
    observedGeneration: status?.observedGeneration,
    phase: status?.phase,
    observed: { ...status?.observed, lastSeen: undefined },
    conditions: status?.conditions,
  });

export const createFleet = ({
  api,
  metrics,
  ping,
  sync,
  leading,
  log,
  now = () => new Date(),
}: FleetDependencies) => {
  let conflicts = new Map<string, string>();
  // The persisted lastSeen is refreshed only every few minutes, so the outage
  // grace runs from the latest answer this replica saw.
  const answered = new Map<string, string>();
  // Set on the first pass after taking the lease; the outage grace never starts
  // before it.
  let leadingSince: string | undefined;

  const ensureLeading = () => {
    if (!leading()) throw new LeadershipLost("The lease was lost");
  };

  const statusChanged = (host: GpuHost, status: HostStatus) => {
    if (withoutLastSeen(status) !== withoutLastSeen(host.status)) return true;
    const written = Date.parse(host.status?.observed?.lastSeen ?? "");
    const seen = Date.parse(status.observed?.lastSeen ?? "");
    return seen - written >= LAST_SEEN_REFRESH_MS;
  };

  const reconcileHost = async (host: GpuHost) => {
    const id = host.spec.instanceId;
    let serviceError: string | undefined;
    let draining: number | undefined;

    ensureLeading();
    try {
      const change = await reconcileService(api, host);
      if (change !== "unchanged") {
        metrics.serviceChanges.inc({ change });
        log({ event: "gpu_host_service", instance_id: id, change });
      }
    } catch (error) {
      serviceError = `The egress Service could not be reconciled: ${(error as Error).message}`;
    }

    ensureLeading();
    if (host.metadata.deletionTimestamp) {
      const drain = await releaseIfDrained(api, host);
      log({
        event: "gpu_host_draining",
        instance_id: id,
        pods: drain.remaining,
      });
      if (drain.released) return { id, status: undefined };
      draining = drain.remaining;
    } else {
      await holdUntilDrained(api, host);
    }

    const observation = await ping(id);
    const time = now();
    if (observation.reachable) answered.set(id, time.toISOString());
    // Only a host answering as itself is uncordoned after a retirement.
    if (
      !host.metadata.deletionTimestamp &&
      observation.reachable &&
      observation.instanceId === id
    ) {
      ensureLeading();
      if (await uncordonIfReturned(api, host))
        log({ event: "gpu_host_uncordoned", instance_id: id });
    }

    const conflict = conflicts.get(id);
    const lastAnswered = answered.get(id);
    const status = hostStatus(
      host,
      {
        observation,
        ...(lastAnswered && { lastAnswered }),
        ...(leadingSince && { leadingSince }),
        ...(serviceError && { serviceError }),
        ...(conflict && { conflict }),
        ...(draining !== undefined && { draining }),
      },
      time,
    );
    if (statusChanged(host, status)) {
      ensureLeading();
      await api.mergePatch(`${GPU_HOSTS}/${host.metadata.name}/status`, {
        status,
      });
    }
    return { id, status };
  };

  const reportInvalid = async ({
    name,
    reported,
  }: {
    name: string;
    reported: boolean;
  }) => {
    if (!name || reported) return;
    ensureLeading();
    const time = now().toISOString();
    await api
      .mergePatch(`${GPU_HOSTS}/${name}/status`, {
        status: {
          phase: "Degraded",
          conditions: [
            {
              type: "Degraded",
              status: "True",
              reason: "InvalidSpec",
              message: "The operator cannot read this GpuHost",
              lastTransitionTime: time,
            },
          ],
        },
      })
      .catch(() => undefined);
  };

  const reconcile = async () => {
    leadingSince ??= now().toISOString();
    try {
      const { hosts, invalid } = parseHosts(await api.list(GPU_HOSTS));
      for (const item of invalid) {
        log({ event: "gpu_host_invalid", name: item.name });
        await reportInvalid(item);
      }
      const results = await Promise.all(hosts.map(reconcileHost));

      metrics.hosts.reset();
      metrics.degraded.reset();
      for (const { id, status } of results) {
        if (!status) continue;
        metrics.hosts.inc({ phase: status.phase ?? "Pending" });
        const degraded = status.conditions?.find(
          (item) => item.type === "Degraded" && item.status === "True",
        );
        if (degraded)
          metrics.degraded.set(
            { instance_id: id, reason: degraded.reason ?? "Unknown" },
            1,
          );
      }
      for (const { name } of invalid)
        metrics.degraded.set({ instance_id: name, reason: "InvalidSpec" }, 1);
      metrics.reconciled.set(now().getTime() / 1000);
    } catch (error) {
      if (error instanceof LeadershipLost) return;
      metrics.reconcileErrors.inc();
      log({
        event: "gpu_fleet_reconcile_failed",
        error: (error as Error).message,
      });
    }
  };

  const syncDatabase = async () => {
    try {
      // Resolving can throw on a malformed credential; that is a sync failure,
      // not a reason to stop reconciling Services.
      const syncFleet = sync();
      metrics.postgresConfigured.set(syncFleet ? 1 : 0);
      if (!syncFleet) return;

      const items = await api.list(GPU_HOSTS);
      const { hosts } = parseHosts(items);
      // A host missing from the list would be retired, so sync only a fully read fleet.
      if (!items.length || hosts.length !== items.length) {
        log({
          event: "gpu_instance_sync_skipped",
          listed: items.length,
          valid: hosts.length,
        });
        return;
      }

      ensureLeading();
      const result = await syncFleet(hosts.map(fleetHost), ensureLeading);
      conflicts = new Map(
        result.conflicts.map(({ instanceId, reason }) => [instanceId, reason]),
      );
      for (const change of [
        "inserted",
        "restored",
        "retired",
        "updated",
      ] as const)
        for (const instanceId of result[change]) {
          metrics.postgresChanges.inc({ change });
          log({ event: "gpu_instance_row", change, instance_id: instanceId });
        }
      for (const { instanceId, reason } of result.conflicts)
        log({
          event: "gpu_instance_conflict",
          instance_id: instanceId,
          reason,
        });
      metrics.postgresConflicts.set(result.conflicts.length);
      metrics.postgresSynced.set(now().getTime() / 1000);
    } catch (error) {
      if (error instanceof LeadershipLost) return;
      log({
        event: "gpu_instance_sync_failed",
        error: (error as Error).message,
      });
    }
  };

  // A stale series on a former leader would keep an alert firing.
  const standDown = () => {
    for (const gauge of [
      metrics.hosts,
      metrics.degraded,
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
    metrics.postgresConflicts.set(0);
    conflicts = new Map();
    answered.clear();
    leadingSince = undefined;
  };

  return { reconcile, syncDatabase, standDown };
};
