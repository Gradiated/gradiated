import { useQueryClient } from "@tanstack/react-query";

import { updateWorkspace } from "@/api/queries";
import type { components } from "@/api/schema";
import { useProductContext } from "@/hooks/use-product-context";
import { queryKeys } from "@/lib/query-keys";
import { canManageOrganization } from "@/lib/roles";
import { NameSetting } from "./name-setting";
import { SettingsHeader } from "./settings-layout";

export const WorkspaceSettingsPage = () => {
  const { organizationId, workspaceId, workspaces, selectedOrganization } =
    useProductContext();
  const client = useQueryClient();
  const workspace = workspaces.find((row) => row.id === workspaceId);

  const save = async (name: string) => {
    const updated = await updateWorkspace(organizationId, workspaceId, {
      name,
    });
    client.setQueryData<components["schemas"]["WorkspaceList"]>(
      queryKeys.workspaces(organizationId),
      (current) =>
        current && {
          ...current,
          data: current.data.map((row) =>
            row.id === updated.id ? updated : row,
          ),
        },
    );
  };

  return (
    <>
      <SettingsHeader
        title="Workspace"
        description="Settings for the workspace you have selected."
      />
      {workspace ? (
        <NameSetting
          key={`${workspace.id}:${workspace.name}`}
          label="Workspace name"
          savedName={workspace.name}
          canEdit={canManageOrganization(selectedOrganization)}
          onSave={save}
          successMessage="Workspace renamed."
        />
      ) : (
        <p role="status">Loading workspace settings…</p>
      )}
    </>
  );
};
