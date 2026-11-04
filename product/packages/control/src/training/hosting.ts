import type { ControlDatabase } from "../db/client.js";
import { ControlServiceError } from "../errors.js";
import type { AdapterDownloads } from "./downloads.js";
import type { TaskVersionRecord } from "./records.js";
import { createTrainingStore } from "./store.js";

export const requireLoadableAdapter = (version: TaskVersionRecord) => {
  if (
    !(
      version.adapter.validated_base_model_revision ??
      version.adapter.base_model_revision
    ) ||
    version.adapter.size_bytes <= 0
  )
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
    async grant(workspaceId: string, versionName: string) {
      const row = await records.getHostingVersion(workspaceId, versionName);
      if (!row)
        throw new ControlServiceError(
          "not_found",
          "The version was not found.",
        );

      requireLoadableAdapter(row.version);
      const adapter = row.version.adapter;
      const download = await downloads.sign(
        adapter.artifact_uri,
        row.version.trainingRunId ?? row.version.id,
        adapter.size_bytes,
        adapter.sha256,
      );

      return { ...row, download };
    },

    async productionVersions(baseModelId: string) {
      const versions = await records.listProductionVersions(baseModelId);

      return versions.map((version) => ({
        workspace_id: version.workspaceId,
        version_name: version.name,
      }));
    },
  };
};

export type AdapterHostingService = ReturnType<
  typeof createAdapterHostingService
>;
