import type { ControlDatabase } from "../db/client.js";
import { catalogModels, trainingOnlyModels } from "./models/index.js";
import { createCatalogService, type CatalogModelInput } from "./service.js";

// Git owns the catalog: every pass rewrites each defined model, so an edit made
// directly in the database is put back.
export const applyCatalog = async (
  database: ControlDatabase,
  definitions: readonly CatalogModelInput[] = [
    ...catalogModels,
    ...trainingOnlyModels(),
  ],
): Promise<{ applied: number; unmanaged: string[] }> => {
  const catalog = createCatalogService(database);
  for (const definition of definitions) {
    await catalog.upsertModel(definition);
  }

  const defined = new Set(definitions.map((definition) => definition.id));
  const stored = await catalog.listModels();

  return {
    applied: definitions.length,
    unmanaged: stored.map((model) => model.id).filter((id) => !defined.has(id)),
  };
};
