import { sql } from "drizzle-orm";
import type { ControlDatabase } from "../db/client.js";
import {
  catalogModels,
  legacyModels,
  trainingOnlyModels,
} from "./models/index.js";
import { ModelRecordSchema } from "./records.js";
import { createCatalogService, type CatalogModelInput } from "./service.js";

// Git owns the catalog: every pass rewrites each defined model, so an edit made
// directly in the database is put back.
export const applyCatalog = async (
  database: ControlDatabase,
  definitions: readonly CatalogModelInput[] = [
    ...catalogModels,
    ...legacyModels,
    ...trainingOnlyModels(),
  ],
): Promise<{ applied: number; unmanaged: string[] }> =>
  database.transaction(async (tx) => {
    await tx.execute(sql`lock table models in share row exclusive mode`);

    const catalog = createCatalogService(tx);
    const defined = new Set(definitions.map((definition) => definition.id));
    const unmanaged = (
      await catalog.listModels({ includeRetired: true })
    ).filter((model) => !defined.has(model.id));
    const resulting = [...definitions, ...unmanaged];
    const names = new Set(
      resulting
        .filter((model) => model.status !== "retired")
        .map((model) => model.id),
    );
    for (const definition of resulting) {
      for (const alias of ModelRecordSchema.shape.aliases.parse(
        definition.aliases,
      )) {
        if (alias === definition.id || names.has(alias)) {
          throw new Error(`Conflicting model alias: ${alias}`);
        }

        names.add(alias);
      }
    }

    for (const definition of definitions) {
      await catalog.upsertModel(definition);
    }

    return {
      applied: definitions.length,
      unmanaged: unmanaged
        .filter((model) => model.status !== "retired")
        .map((model) => model.id),
    };
  });
