import { createDeploymentStore } from "./store.js";
import type { ModelDeploymentRelease } from "@gradiated/contracts";
import { and, eq, inArray, isNull, notInArray, or, sql } from "drizzle-orm";

import {
  ModelDeploymentRecordSchema,
  ModelDeploymentInsertSchema,
} from "../catalog/records.js";
import type { ControlDatabase } from "../db/client.js";
import { instances, modelDeployments, models } from "../db/schema/index.js";
import { privateServingUrl } from "../instances/endpoints.js";

export interface NomadAllocation {
  readonly allocationId: string;
  readonly nodeId: string;
  readonly modelId: string;
  readonly release: ModelDeploymentRelease;
  readonly draining: boolean;
  readonly verificationPending?: boolean;
  readonly replica?: {
    readonly key: string;
    readonly child: boolean;
    readonly order: number;
  };
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

export const NOMAD_RECONCILE_LOCK = "gradiated-nomad-deployments-v1";

type Instance = typeof instances.$inferSelect;

const hostProxyUrl = (instance: Instance): string | null => {
  return instance.servingUrl === privateServingUrl(instance.id)
    ? instance.servingUrl
    : null;
};

export const createNomadDeploymentStore = (
  database: ControlDatabase,
): NomadDeploymentStore => ({
  ...createDeploymentStore(database),
  reconcile: (nomad) =>
    database.transaction(async (tx) => {
      const {
        rows: [lock],
      } = await tx.execute<{ acquired: boolean }>(
        sql`select pg_try_advisory_xact_lock(hashtext(${NOMAD_RECONCILE_LOCK})) as acquired`,
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

      const withoutPrivateEndpoint = unplaced
        .filter(
          (allocation) =>
            allocation.reason === "provider_has_no_serving_address",
        )
        .map((allocation) => allocation.allocationId);
      if (withoutPrivateEndpoint.length)
        await tx
          .update(modelDeployments)
          .set({ status: "unavailable", updatedAt: sql`now()` })
          .where(inArray(modelDeployments.id, withoutPrivateEndpoint));

      for (const value of rows) {
        const row = ModelDeploymentInsertSchema.parse(value);

        await tx
          .insert(modelDeployments)
          .values(row)
          .onConflictDoUpdate({
            target: modelDeployments.id,
            setWhere: eq(modelDeployments.orchestrator, "nomad"),
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

      const slotted = allocations.filter((allocation) => allocation.replica);
      if (slotted.length) {
        const available = new Set(
          (
            await tx
              .select({ id: modelDeployments.id })
              .from(modelDeployments)
              .where(
                and(
                  eq(modelDeployments.status, "available"),
                  inArray(
                    modelDeployments.id,
                    slotted.map((allocation) => allocation.allocationId),
                  ),
                ),
              )
          ).map((row) => row.id),
        );
        const selected = new Map<string, NomadAllocation>();
        const superseded: string[] = [];
        for (const allocation of slotted) {
          if (!available.has(allocation.allocationId)) continue;
          const key = `${allocation.modelId}:${allocation.replica!.key}`;
          const previous = selected.get(key);
          if (
            !previous ||
            Number(allocation.replica!.child) >
              Number(previous.replica!.child) ||
            (allocation.replica!.child === previous.replica!.child &&
              allocation.replica!.order > previous.replica!.order)
          ) {
            if (previous) superseded.push(previous.allocationId);
            selected.set(key, allocation);
          } else superseded.push(allocation.allocationId);
        }
        if (superseded.length)
          await tx
            .update(modelDeployments)
            .set({ status: "draining", updatedAt: sql`now()` })
            .where(inArray(modelDeployments.id, superseded));
      }

      // A list filtered by ACL or cut short would look like every replica stopped,
      // so a row goes only once Nomad confirms its allocation is gone.
      const listed = allocations.map((allocation) => allocation.allocationId);
      const unlisted = await tx
        .select({ id: modelDeployments.id })
        .from(modelDeployments)
        .where(
          and(
            eq(modelDeployments.orchestrator, "nomad"),
            listed.length ? notInArray(modelDeployments.id, listed) : undefined,
          ),
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
