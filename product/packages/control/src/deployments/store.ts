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
  runtimeMetricsTargets(): Promise<
    { id: string; modelId: string; serviceUrl: string }[]
  >;
  adapterMetricsTargets(): Promise<
    { id: string; modelId: string; serviceUrl: string }[]
  >;
  adapterProbeTargets(modelId: string): Promise<
    {
      id: string;
      modelId: string;
      serviceUrl: string;
      release: ModelDeploymentRelease;
    }[]
  >;
  verificationReplicas(
    modelId: string,
    deploymentIds: readonly string[],
  ): Promise<
    (ModelReplica & { status: "available" | "unavailable" | "draining" })[]
  >;
}
const hostProxyUrl = (instance: typeof instances.$inferSelect) =>
  privateServingUrl(instance.id);

const privateAllocations = async (
  database: ControlDatabase,
  adaptersOnly: boolean,
  modelId?: string,
) => {
  const rows = await database
    .select({
      id: modelDeployments.id,
      modelId: modelDeployments.modelId,
      serviceUrl: modelDeployments.serviceUrl,
      release: modelDeployments.release,
      instance: instances,
    })
    .from(modelDeployments)
    .innerJoin(instances, eq(modelDeployments.instanceId, instances.id))
    .where(
      and(
        adaptersOnly
          ? sql`${modelDeployments.release}->>'lora_enabled' = 'true'`
          : undefined,
        eq(modelDeployments.status, "available"),
        isNull(instances.retiredAt),
        modelId === undefined
          ? undefined
          : eq(modelDeployments.modelId, modelId),
      ),
    );

  return ModelDeploymentRecordSchema.pick({
    id: true,
    modelId: true,
    serviceUrl: true,
    release: true,
  })
    .array()
    .parse(
      rows.filter((row) => {
        const proxy = hostProxyUrl(row.instance);
        return proxy !== null && row.serviceUrl === `${proxy}/alloc/${row.id}`;
      }),
    );
};
export const createDeploymentStore = (
  database: ControlDatabase,
): DeploymentStore => ({
  runtimeMetricsTargets: async () =>
    (await privateAllocations(database, false)).map(
      ({ id, modelId, serviceUrl }) => ({ id, modelId, serviceUrl }),
    ),
  adapterMetricsTargets: async () =>
    (await privateAllocations(database, true)).map(
      ({ id, modelId, serviceUrl }) => ({
        id,
        modelId,
        serviceUrl,
      }),
    ),

  adapterProbeTargets: async (modelId) =>
    privateAllocations(
      database,
      true,
      ModelDeploymentRecordSchema.shape.modelId.parse(modelId),
    ),

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
