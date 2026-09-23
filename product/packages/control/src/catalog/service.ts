import { getTableColumns, ne } from "drizzle-orm";

import {
  GatewayModelDeploymentSchema,
  ModelPropertiesInputSchema,
  type ModelDeploymentRelease,
  type ModelPropertiesInput,
} from "@gradiated/contracts";

import type { ControlDatabase } from "../db/client.js";
import { modelDeployments, models } from "../db/schema/index.js";
import { requireRow } from "../require-row.js";

export type ModelRecord = typeof models.$inferSelect;

const { instanceId: _instanceId, ...deploymentColumns } =
  getTableColumns(modelDeployments);

export type ModelDeploymentRecord = Omit<
  typeof modelDeployments.$inferSelect,
  "instanceId"
>;

export interface CatalogService {
  listModels(): Promise<ModelRecord[]>;
  upsertModel(input: {
    id: string;
    name: string;
    status: ModelRecord["status"];
    properties: ModelPropertiesInput;
  }): Promise<ModelRecord>;
  upsertModelDeployment(input: {
    id: string;
    modelId: string;
    status: ModelDeploymentRecord["status"];
    provider: string;
    region: string;
    faultDomain: string;
    serviceUrl: string;
    release: ModelDeploymentRelease;
  }): Promise<ModelDeploymentRecord>;
}

export const createCatalogService = (
  database: ControlDatabase,
): CatalogService => ({
  async listModels() {
    return database
      .select()
      .from(models)
      .where(ne(models.status, "retired"))
      .orderBy(models.createdAt, models.id);
  },

  async upsertModel(input) {
    const now = new Date();
    const properties = ModelPropertiesInputSchema.parse(input.properties);

    const rows = await database
      .insert(models)
      .values({ ...input, properties, createdAt: now, updatedAt: now })
      .onConflictDoUpdate({
        target: models.id,
        set: {
          name: input.name,
          status: input.status,
          properties,
          updatedAt: now,
        },
      })
      .returning();

    return requireRow(rows, "The model upsert returned no row.");
  },

  async upsertModelDeployment(input) {
    const validated = GatewayModelDeploymentSchema.parse({
      id: input.id,
      status: input.status,
      provider: input.provider,
      region: input.region,
      fault_domain: input.faultDomain,
      service_url: input.serviceUrl,
      release: input.release,
    });
    const now = new Date();
    const values = {
      status: validated.status,
      provider: validated.provider,
      region: validated.region,
      faultDomain: validated.fault_domain,
      serviceUrl: validated.service_url,
      release: validated.release,
      updatedAt: now,
    };

    const rows = await database
      .insert(modelDeployments)
      .values({
        ...values,
        id: validated.id,
        modelId: input.modelId,
        createdAt: now,
      })
      .onConflictDoUpdate({ target: modelDeployments.id, set: values })
      .returning(deploymentColumns);

    return requireRow(rows, "The model deployment upsert returned no row.");
  },
});
