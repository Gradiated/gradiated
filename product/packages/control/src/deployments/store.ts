import type { ModelDeploymentRelease } from "@gradiated/contracts";
import { and, eq, inArray, isNull, or, sql } from "drizzle-orm";
import { ModelDeploymentRecordSchema } from "../catalog/records.js";
import type { ControlDatabase } from "../db/client.js";
import { instances, modelDeployments } from "../db/schema/index.js";
import { privateServingUrl } from "../instances/endpoints.js";

export const DEPLOYMENT_RECONCILE_LOCK = "gradiated-kubernetes-deployments-v1";

export interface ModelReplica {
  readonly id: string;
  readonly modelId: string;
  readonly release: ModelDeploymentRelease;
}
export interface DeploymentStore {
  replicas(): Promise<ModelReplica[]>;
  adapterMetricsTargets(): Promise<
    { id: string; modelId: string; serviceUrl: string }[]
  >;
  verificationReplicas(
    modelId: string,
    deploymentIds: readonly string[],
  ): Promise<
    (ModelReplica & { status: "available" | "unavailable" | "draining" })[]
  >;
}
const hostProxyUrl = (instance: typeof instances.$inferSelect) =>
  instance.servingUrl === privateServingUrl(instance.id)
    ? instance.servingUrl
    : null;
export const createDeploymentStore = (
  database: ControlDatabase,
): DeploymentStore => ({
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
});
