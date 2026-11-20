import { applyCatalog, type ControlDatabase } from "@gradiated/control";

import { serviceLog } from "./logging.js";

export const createCatalogApply = (
  database: ControlDatabase,
  apply: typeof applyCatalog = applyCatalog,
) => {
  let reported = "";

  return async (): Promise<void> => {
    const { unmanaged, skipped } = await apply(database);
    const current = JSON.stringify([[...unmanaged].sort(), skipped]);
    if (current === reported) return;

    reported = current;
    for (const modelId of unmanaged) {
      serviceLog("warn", "catalog_model_unmanaged", { model_id: modelId });
    }
    // An owned model waits for its organization to exist in this environment.
    for (const { id, reason } of skipped) {
      serviceLog("warn", "catalog_model_skipped", {
        model_id: id,
        reason,
      });
    }
  };
};
