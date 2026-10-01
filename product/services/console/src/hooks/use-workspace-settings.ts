import { useQueryClient } from "@tanstack/react-query";
import { updateWorkspace, type UpdateWorkspace } from "@/api/queries";
import type { components } from "@/api/schema";
import { useProductContext } from "./use-product-context";
import { useOptimisticPatch } from "./use-optimistic-patch";
import {
  workspaceSettingsKey,
  type WorkspaceSettingsPatch,
} from "@/lib/workspace-settings";
import { queryKeys } from "@/lib/query-keys";

export const useWorkspaceSettings = () => {
  const { organizationId, workspaceId, workspaces, selectedOrganization } =
    useProductContext();
  const client = useQueryClient();
  const queryKey = queryKeys.workspaces(organizationId);
  const save = useOptimisticPatch({
    mutationKey: workspaceSettingsKey(organizationId),
    queryKey,
    mutationFn: ({ id, patch }: WorkspaceSettingsPatch) =>
      updateWorkspace(organizationId, id, patch),
    commit: (workspace, { id }) => {
      client.setQueryData<components["schemas"]["WorkspaceList"]>(
        queryKey,
        (current) =>
          current && {
            ...current,
            data: current.data.map((row) =>
              row.id === id ? { ...row, ...workspace } : row,
            ),
          },
      );
    },
  });

  return {
    workspace: workspaces.find((row) => row.id === workspaceId),
    save: {
      ...save,
      mutate: (patch: UpdateWorkspace) =>
        save.mutate({ id: workspaceId, patch }),
    },
    canEdit:
      selectedOrganization?.status === "active" &&
      ["owner", "admin"].includes(selectedOrganization.role),
  };
};
