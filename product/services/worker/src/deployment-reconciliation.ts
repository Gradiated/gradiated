import type { DeploymentStore } from "@gradiated/control";
import type { WorkerMetrics } from "./metrics.js";
import { countReadyReplicas } from "./replica-readiness.js";

export interface ReplicaReadiness {
  readonly store: Pick<DeploymentStore, "replicas">;
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
