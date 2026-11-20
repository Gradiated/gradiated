import { and, eq, getTableColumns, isNull, ne, sql } from "drizzle-orm";
import {
  GatewayModelDeploymentSchema,
  ModelPropertiesInputSchema,
} from "@gradiated/contracts";
import type { ControlDatabase } from "../db/client.js";
import { modelDeployments, models } from "../db/schema/index.js";
import { ControlServiceError } from "../errors.js";
import { requireRow } from "../require-row.js";
import { releaseServesType } from "./protocol.js";
import type { CatalogService } from "./service.js";
import { ModelRecordSchema, ModelDeploymentRecordSchema } from "./records.js";

const { instanceId: _instanceId, ...deploymentColumns } =
  getTableColumns(modelDeployments);

export const createCatalogStore = (
  database: ControlDatabase,
): CatalogService => ({
  async listModels(options = {}) {
    const rows = await database
      .select()
      .from(models)
      .where(
        and(
          options.includeRetired ? undefined : ne(models.status, "retired"),
          // Organization-owned models stay out unless the caller asks for them,
          // so no listing can publish one by accident.
          options.includeOrganizationModels
            ? undefined
            : isNull(models.organizationId),
        ),
      )
      .orderBy(models.createdAt, models.id);

    return ModelRecordSchema.array().parse(rows);
  },

  async upsertModel(input) {
    // A definition's owner slug is resolved by applyCatalog; writing one
    // directly would drop the owner and publish the model.
    if ("owner" in input)
      throw new Error("Apply an owned catalog definition with applyCatalog.");
    const now = new Date();
    const properties = ModelPropertiesInputSchema.parse(input.properties);

    const { tokenizer, ...model } = input;
    const record = ModelRecordSchema.parse({
      ...model,
      properties,
      openrouterModelId: input.openrouterModelId ?? null,
      tokenizerPath: tokenizer?.path ?? null,
      tokenizerRevision: tokenizer?.revision ?? null,
      organizationId: input.organizationId ?? null,
      type: input.type,
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
          aliases: record.aliases,
          status: record.status,
          properties: record.properties,
          openrouterModelId: record.openrouterModelId,
          tokenizerPath: record.tokenizerPath,
          tokenizerRevision: record.tokenizerRevision,
          type: record.type,
          updatedAt: now,
        },
        // A model's owner is fixed when it is first written, as gateways cache
        // records under the ID; a write with another owner returns no row.
        setWhere: sql`${models.organizationId} is not distinct from ${record.organizationId}`,
      })
      .returning();
    const stored = ModelRecordSchema.parse(
      requireRow(rows, "The model upsert returned no row."),
    );

    // A changed type withdraws the deployments that no longer serve it, in the
    // same transaction, so the gateway never routes to the other interface.
    await database
      .update(modelDeployments)
      .set({ status: "unavailable", updatedAt: now })
      .where(
        and(
          eq(modelDeployments.modelId, stored.id),
          ne(modelDeployments.status, "unavailable"),
          sql`(coalesce(${modelDeployments.release}->>'protocol', '') = 'system_one') <> ${stored.type === "decision"}`,
        ),
      );

    return stored;
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
    const [model] = await database
      .select({ type: models.type })
      .from(models)
      .where(eq(models.id, record.modelId));
    if (model && !releaseServesType(record.release, model.type))
      throw new ControlServiceError(
        "conflict",
        `This release does not serve the model's ${model.type} interface.`,
      );

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
