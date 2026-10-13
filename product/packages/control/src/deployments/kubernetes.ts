import { ModelDeploymentReleaseSchema } from "@gradiated/contracts";
import { and, eq, isNull, sql } from "drizzle-orm";
import { z } from "zod";

import {
  ModelDeploymentInsertSchema,
  ModelDeploymentRecordSchema,
} from "../catalog/records.js";
import type { ControlDatabase } from "../db/client.js";
import { instances, modelDeployments, models } from "../db/schema/index.js";
import { DEPLOYMENT_RECONCILE_LOCK } from "./store.js";
import { privateServingUrl } from "../instances/endpoints.js";

export const KubernetesDeploymentSchema = z.object({
  id: z.uuid(),
  name: z.string().min(1),
  instanceId: z.uuid(),
  modelId: z.string().min(1),
  release: ModelDeploymentReleaseSchema,
  qualified: z.boolean(),
  draining: z.boolean(),
});

export type KubernetesDeployment = z.infer<typeof KubernetesDeploymentSchema>;

export interface KubernetesDeploymentView {
  running(): Promise<readonly KubernetesDeployment[]>;
  isGone(id: string): Promise<boolean>;
}

export const createKubernetesDeploymentStore = (database: ControlDatabase) => ({
  reconcile: (view: KubernetesDeploymentView) =>
    database.transaction(async (tx) => {
      const {
        rows: [lock],
      } = await tx.execute<{ acquired: boolean }>(
        sql`select pg_try_advisory_xact_lock(hashtext(${DEPLOYMENT_RECONCILE_LOCK})) as acquired`,
      );
      if (!lock?.acquired) return null;

      const current = KubernetesDeploymentSchema.array().parse(
        await view.running(),
      );
      const listed = new Set(current.map((pod) => pod.id));
      let written = 0;
      const withdraw = (id: string) =>
        tx
          .update(modelDeployments)
          .set({
            ...ModelDeploymentRecordSchema.pick({ status: true }).parse({
              status: "unavailable",
            }),
            updatedAt: sql`now()`,
          })
          .where(eq(modelDeployments.id, id));

      for (const pod of current) {
        const [host] = await tx
          .select()
          .from(instances)
          .where(
            and(eq(instances.id, pod.instanceId), isNull(instances.retiredAt)),
          );
        const [model] = await tx
          .select({ id: models.id })
          .from(models)
          .where(eq(models.id, pod.modelId));
        if (!host || !model) {
          await withdraw(pod.id);
          continue;
        }

        const row = ModelDeploymentInsertSchema.parse({
          id: pod.id,
          instanceId: host.id,
          modelId: pod.modelId,
          status: pod.draining
            ? "draining"
            : pod.qualified
              ? "available"
              : "unavailable",
          provider: host.provider,
          region: host.region ?? "unknown",
          faultDomain:
            host.faultDomain ?? `${host.provider}:${host.providerInstanceId}`,
          serviceUrl: `${privateServingUrl(host.id)}/alloc/${pod.id}`,
          release: pod.release,
        });
        await tx
          .insert(modelDeployments)
          .values(row)
          .onConflictDoUpdate({
            target: modelDeployments.id,
            set: { ...row, updatedAt: sql`now()` },
          });
        written += 1;
      }

      const owned = await tx
        .select({ id: modelDeployments.id })
        .from(modelDeployments);
      for (const { id } of owned) {
        if (!listed.has(id) && (await view.isGone(id))) {
          await tx.delete(modelDeployments).where(eq(modelDeployments.id, id));
        } else if (!listed.has(id)) {
          await withdraw(id);
        }
      }
      return { written };
    }),
});
