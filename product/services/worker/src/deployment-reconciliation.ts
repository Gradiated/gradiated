import type { NomadDeploymentStore } from "@gradiated/control";

import { serviceLog } from "./logging.js";
import type { WorkerMetrics } from "./metrics.js";
import { countReadyReplicas } from "./replica-readiness.js";
import {
  allocationIsGone,
  readModelAllocations,
  type NomadGet,
} from "./nomad-allocations.js";

export interface DeploymentReconciliation {
  readonly store: Pick<NomadDeploymentStore, "reconcile">;
  readonly get: NomadGet;
  readonly metrics: Pick<WorkerMetrics, "recordReconciliation">;
}

export interface ReplicaReadiness {
  readonly store: Pick<NomadDeploymentStore, "replicas">;
  readonly valkey: {
    hGetAll(key: string): Promise<Record<string, string>>;
  };
  readonly metrics: Pick<WorkerMetrics, "recordReplicaReadiness">;
}

export const observeReplicaReadiness = async ({
  store,
  valkey,
  metrics,
}: ReplicaReadiness): Promise<void> => {
  metrics.recordReplicaReadiness(
    await countReadyReplicas(await store.replicas(), (digest) =>
      valkey.hGetAll(`deployment-status:{${digest}}`),
    ),
  );
};

export const reconcileDeployments = async ({
  store,
  get,
  metrics,
}: DeploymentReconciliation): Promise<void> => {
  const skipped: { allocationId: string; modelId: string }[] = [];
  const result = await store.reconcile({
    running: () =>
      readModelAllocations(get, (allocationId, modelId) =>
        skipped.push({ allocationId, modelId }),
      ),
    isGone: (allocationId) => allocationIsGone(get, allocationId),
  });
  if (!result) return;

  const unrouted = [
    ...skipped.map((allocation) => ({
      ...allocation,
      reason: "invalid_release_meta",
    })),
    ...result.unplaced,
  ];
  const counts: Record<string, number> = {};
  for (const { allocationId, modelId, reason } of unrouted) {
    counts[reason] = (counts[reason] ?? 0) + 1;
    serviceLog("warn", "nomad_allocation_unrouted", {
      allocation_id: allocationId,
      model_id: modelId,
      reason,
    });
  }
  metrics.recordReconciliation(result.written, counts);
};
