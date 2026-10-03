import type { ModelDeploymentRelease } from "@gradiated/contracts";
import { and, eq, inArray, isNull, notInArray, or, sql } from "drizzle-orm";

import {
  ModelDeploymentRecordSchema,
  ModelDeploymentInsertSchema,
} from "../catalog/records.js";
import type { ControlDatabase } from "../db/client.js";
import { instances, modelDeployments, models } from "../db/schema/index.js";

export interface NomadAllocation {
  readonly allocationId: string;
  readonly nodeId: string;
  readonly modelId: string;
  readonly release: ModelDeploymentRelease;
  readonly draining: boolean;
  readonly verificationPending?: boolean;
}

export type UnplacedReason =
  | "node_not_registered"
  | "model_not_in_catalog"
  | "provider_has_no_serving_address";

export interface ReconcileResult {
  readonly written: number;
  readonly removed: number;
  readonly unplaced: {
    allocationId: string;
    modelId: string;
    reason: UnplacedReason;
  }[];
}

export interface NomadView {
  running(): Promise<readonly NomadAllocation[]>;
  isGone(allocationId: string): Promise<boolean>;
}

export interface NomadReplica {
  readonly id: string;
  readonly modelId: string;
  readonly release: ModelDeploymentRelease;
}

export interface NomadDeploymentStore {
  /** Returns null when another worker is running the pass. */
  reconcile(nomad: NomadView): Promise<ReconcileResult | null>;
  replicas(): Promise<NomadReplica[]>;
  adapterMetricsTargets(): Promise<
    { id: string; modelId: string; serviceUrl: string }[]
  >;
  verificationReplicas(
    modelId: string,
    deploymentIds: readonly string[],
  ): Promise<
    (NomadReplica & {
      status: "available" | "unavailable" | "draining";
    })[]
  >;
}

const PASS_LOCK = "gradiated-nomad-deployments-v1";
const HOST_PROXY_PORT = 8888;

type Instance = typeof instances.$inferSelect;

// How the gateway reaches a host's proxy differs by provider.
const hostProxyUrl = (instance: Instance): string | null => {
  switch (instance.provider) {
    case "runpod":
      return `https://${instance.providerInstanceId}-${HOST_PROXY_PORT}.proxy.runpod.net`;
    default:
      return null;
  }
};

export const createNomadDeploymentStore = (
  database: ControlDatabase,
): NomadDeploymentStore => ({
  adapterMetricsTargets: async () => {
    const rows = await database
      .select({
        id: modelDeployments.id,
        modelId: modelDeployments.modelId,
        serviceUrl: modelDeployments.serviceUrl,
        instance: instances,
      })
      .from(modelDeployments)
      .innerJoin(instances, eq(modelDeployments.instanceId, instances.id))
      .where(
        and(
          sql`${modelDeployments.release}->>'lora_enabled' = 'true'`,
          eq(modelDeployments.status, "available"),
          isNull(instances.retiredAt),
        ),
      );

    return ModelDeploymentRecordSchema.pick({
      id: true,
      modelId: true,
      serviceUrl: true,
    })
      .array()
      .parse(
        rows.filter((row) => {
          const proxy = hostProxyUrl(row.instance);
          return (
            proxy !== null && row.serviceUrl === `${proxy}/alloc/${row.id}`
          );
        }),
      );
  },

  replicas: async () => {
    const rows = await database
      .select({
        id: modelDeployments.id,
        modelId: modelDeployments.modelId,
        release: modelDeployments.release,
      })
      .from(modelDeployments)
      .where(eq(modelDeployments.status, "available"));

    return ModelDeploymentRecordSchema.pick({
      id: true,
      modelId: true,
      release: true,
    })
      .array()
      .parse(rows);
  },

  async verificationReplicas(modelId, deploymentIds) {
    modelId = ModelDeploymentRecordSchema.shape.modelId.parse(modelId);
    const ids = ModelDeploymentRecordSchema.shape.id
      .array()
      .parse(deploymentIds);

    const rows = await database
      .select({
        id: modelDeployments.id,
        modelId: modelDeployments.modelId,
        status: modelDeployments.status,
        release: modelDeployments.release,
      })
      .from(modelDeployments)
      .where(
        and(
          eq(modelDeployments.modelId, modelId),
          or(
            ids.length ? inArray(modelDeployments.id, ids) : undefined,
            eq(modelDeployments.status, "available"),
          ),
        ),
      );

    return ModelDeploymentRecordSchema.pick({
      id: true,
      modelId: true,
      status: true,
      release: true,
    })
      .array()
      .parse(rows);
  },

  reconcile: (nomad) =>
    database.transaction(async (tx) => {
      const {
        rows: [lock],
      } = await tx.execute<{ acquired: boolean }>(
        sql`select pg_try_advisory_xact_lock(hashtext(${PASS_LOCK})) as acquired`,
      );
      if (!lock?.acquired) return null;

      // Read Nomad under the lock so a slower pass cannot write an older view.
      const allocations = await nomad.running();
      const nodeIds = [...new Set(allocations.map((a) => a.nodeId))];
      const modelIds = [...new Set(allocations.map((a) => a.modelId))];
      const hosts = new Map(
        (nodeIds.length
          ? await tx
              .select()
              .from(instances)
              .where(
                and(
                  inArray(instances.nomadNodeId, nodeIds),
                  isNull(instances.retiredAt),
                ),
              )
          : []
        ).map((instance) => [instance.nomadNodeId, instance]),
      );
      const catalogued = new Set(
        (modelIds.length
          ? await tx
              .select({ id: models.id })
              .from(models)
              .where(inArray(models.id, modelIds))
          : []
        ).map((model) => model.id),
      );

      const place = (allocation: NomadAllocation) => {
        const host = hosts.get(allocation.nodeId);
        if (!host) return "node_not_registered" as const;
        if (!catalogued.has(allocation.modelId)) {
          return "model_not_in_catalog" as const;
        }
        const proxy = hostProxyUrl(host);
        if (!proxy) return "provider_has_no_serving_address" as const;

        return {
          id: allocation.allocationId,
          instanceId: host.id,
          modelId: allocation.modelId,
          status: allocation.draining
            ? ("draining" as const)
            : allocation.verificationPending
              ? ("unavailable" as const)
              : ("available" as const),
          provider: host.provider,
          region: host.region ?? "unknown",
          faultDomain:
            host.faultDomain ?? `${host.provider}:${host.providerInstanceId}`,
          serviceUrl: `${proxy}/alloc/${allocation.allocationId}`,
          release: allocation.release,
        };
      };

      const rows: Exclude<ReturnType<typeof place>, UnplacedReason>[] = [];
      const unplaced: ReconcileResult["unplaced"] = [];
      for (const allocation of allocations) {
        const placed = place(allocation);
        if (typeof placed === "string") {
          unplaced.push({
            allocationId: allocation.allocationId,
            modelId: allocation.modelId,
            reason: placed,
          });
        } else {
          rows.push(placed);
        }
      }

      for (const value of rows) {
        const row = ModelDeploymentInsertSchema.parse(value);

        await tx
          .insert(modelDeployments)
          .values(row)
          .onConflictDoUpdate({
            target: modelDeployments.id,
            set: {
              instanceId: row.instanceId,
              modelId: row.modelId,
              // Scaling can attach an unchanged allocation to a new unverified job version.
              status: sql`case when ${row.status} = 'unavailable'
                and ${modelDeployments.status} = 'available'
                and ${modelDeployments.modelId} = ${row.modelId}
                and ${modelDeployments.instanceId} = ${row.instanceId}
                and ${modelDeployments.release} = ${JSON.stringify(row.release)}::jsonb
                then 'available' else ${row.status} end`,
              provider: row.provider,
              region: row.region,
              faultDomain: row.faultDomain,
              serviceUrl: row.serviceUrl,
              release: row.release,
              updatedAt: sql`now()`,
            },
          });
      }

      // A list filtered by ACL or cut short would look like every replica stopped,
      // so a row goes only once Nomad confirms its allocation is gone.
      const listed = allocations.map((allocation) => allocation.allocationId);
      const unlisted = await tx
        .select({ id: modelDeployments.id })
        .from(modelDeployments)
        .where(
          listed.length ? notInArray(modelDeployments.id, listed) : undefined,
        );
      const removed: string[] = [];
      for (const { id } of unlisted) {
        if (await nomad.isGone(id)) removed.push(id);
      }
      if (removed.length) {
        await tx
          .delete(modelDeployments)
          .where(inArray(modelDeployments.id, removed));
      }

      return { written: rows.length, removed: removed.length, unplaced };
    }),
});
