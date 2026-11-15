import { queryOptions } from "@tanstack/react-query";

import {
  getAdapterConfiguration,
  getAdapterWeights,
  getSharedAdapterConfiguration,
  getSharedAdapterWeights,
} from "@/api/training";

// A workspace member's version, or a version reached through a public share link.
export type ExplorerTarget =
  | {
      kind?: "workspace";
      workspaceId: string;
      task: string;
      versionId: string;
      baseModelId: string;
    }
  | { kind: "shared"; versionId: string; signature: string };

export const adapterWeightsQuery = (target: ExplorerTarget) =>
  queryOptions({
    queryKey:
      target.kind === "shared"
        ? ["adapter-weights", "shared", target.versionId, target.signature]
        : [
            "adapter-weights",
            target.workspaceId,
            target.task,
            target.versionId,
          ],
    queryFn: ({ signal }) =>
      target.kind === "shared"
        ? getSharedAdapterWeights(
            { version_id: target.versionId, signature: target.signature },
            signal,
          )
        : getAdapterWeights(
            {
              workspace_id: target.workspaceId,
              task: target.task,
              version_id: target.versionId,
            },
            signal,
          ),
    staleTime: Infinity,
    gcTime: 30 * 60_000,
    retry: 1,
  });

export const baseStructureQuery = (target: ExplorerTarget) =>
  queryOptions({
    queryKey:
      target.kind === "shared"
        ? [
            "adapter-explorer-structure",
            "shared",
            target.versionId,
            target.signature,
          ]
        : [
            "adapter-explorer-structure",
            target.workspaceId,
            target.baseModelId,
          ],
    queryFn: ({ signal }) =>
      target.kind === "shared"
        ? getSharedAdapterConfiguration(
            { version_id: target.versionId, signature: target.signature },
            signal,
          )
        : getAdapterConfiguration(
            target.workspaceId,
            target.baseModelId,
            signal,
          ),
    staleTime: Infinity,
    retry: false,
  });
