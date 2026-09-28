import { applyCatalog, type ControlDatabase } from "@gradiated/control";

import { serviceLog } from "./logging.js";

export const createCatalogApply = (
  database: ControlDatabase,
  apply: typeof applyCatalog = applyCatalog,
) => {
  let reported = "";

  return async (): Promise<void> => {
    const { unmanaged } = await apply(database);
    const current = [...unmanaged].sort().join(",");
    if (current === reported) return;

    reported = current;
    for (const modelId of unmanaged) {
      serviceLog("warn", "catalog_model_unmanaged", { model_id: modelId });
    }
  };
};
