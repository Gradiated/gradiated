import type { ControlDatabase } from "../db/client.js";
import { ControlServiceError } from "../errors.js";
import type { AdapterDownloads } from "./downloads.js";
import type { TaskVersionRecord } from "./records.js";
import { createTrainingStore } from "./store.js";

export const requireLoadableAdapter = (version: TaskVersionRecord) => {
  if (!version.adapter.base_model_revision || version.adapter.size_bytes <= 0)
    throw new ControlServiceError(
      "unavailable",
      "The adapter needs a recorded base revision and a non-empty archive.",
    );
};

export const createAdapterHostingService = (
  database: ControlDatabase,
  downloads: AdapterDownloads,
) => {
  const records = createTrainingStore(database);

  return {
    async grant(workspaceId: string, versionId: string, sha256: string) {
      const row = await records.getHostingVersion(workspaceId, versionId);
      if (!row || row.version.adapter.sha256 !== sha256)
        throw new ControlServiceError(
          "not_found",
          "The version was not found.",
        );

      requireLoadableAdapter(row.version);
      const adapter = row.version.adapter;
      const download = await downloads.sign(
        adapter.artifact_uri,
        row.version.trainingRunId,
        adapter.size_bytes,
        adapter.sha256,
      );

      return { ...row, download };
    },

    async productionVersions(baseModelId: string) {
      const versions = await records.listProductionVersions(baseModelId);

      return versions
        .filter(
          (version) =>
            version.adapter.base_model_revision &&
            version.adapter.size_bytes > 0,
        )
        .map((version) => ({
          workspace_id: version.workspaceId,
          version_id: version.id,
          sha256: version.adapter.sha256,
        }));
    },
  };
};

export type AdapterHostingService = ReturnType<
  typeof createAdapterHostingService
>;
