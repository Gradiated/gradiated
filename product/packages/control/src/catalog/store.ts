import { getTableColumns, ne } from "drizzle-orm";
import {
  GatewayModelDeploymentSchema,
  ModelPropertiesInputSchema,
} from "@gradiated/contracts";
import type { ControlDatabase } from "../db/client.js";
import { modelDeployments, models } from "../db/schema/index.js";
import { requireRow } from "../require-row.js";
import type { CatalogService } from "./service.js";
import { ModelRecordSchema, ModelDeploymentRecordSchema } from "./records.js";

const { instanceId: _instanceId, ...deploymentColumns } =
  getTableColumns(modelDeployments);

export const createCatalogStore = (
  database: ControlDatabase,
): CatalogService => ({
  async listModels() {
    const rows = await database
      .select()
      .from(models)
      .where(ne(models.status, "retired"))
      .orderBy(models.createdAt, models.id);

    return ModelRecordSchema.array().parse(rows);
  },

  async upsertModel(input) {
    const now = new Date();
    const properties = ModelPropertiesInputSchema.parse(input.properties);

    const record = ModelRecordSchema.parse({
      ...input,
      properties,
      createdAt: now,
      updatedAt: now,
    });

    const rows = await database
      .insert(models)
      .values(record)
      .onConflictDoUpdate({
        target: models.id,
        set: {
          name: record.name,
          status: record.status,
          properties: record.properties,
          updatedAt: now,
        },
      })
      .returning();

    return ModelRecordSchema.parse(
      requireRow(rows, "The model upsert returned no row."),
    );
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

    const record = ModelDeploymentRecordSchema.parse({
      ...values,
      id: validated.id,
      modelId: input.modelId,
      createdAt: now,
    });

    const rows = await database
      .insert(modelDeployments)
      .values(record)
      .onConflictDoUpdate({ target: modelDeployments.id, set: values })
      .returning(deploymentColumns);

    return ModelDeploymentRecordSchema.parse(
      requireRow(rows, "The model deployment upsert returned no row."),
    );
  },
});
