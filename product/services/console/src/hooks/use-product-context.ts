import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";

import type { components } from "@/api/schema";
import {
  listWorkspaces,
  type Organization,
  type Workspace,
} from "@/api/queries";
import { useSession } from "@/hooks/use-session";
import { queryKeys } from "@/lib/query-keys";
import { useWorkspaceSelection } from "@/store/workspace-selection";

export const useWorkspaceList = (organizationId: string) =>
  useQuery({
    queryKey: queryKeys.workspaces(organizationId),
    queryFn: () => listWorkspaces(organizationId),
    enabled: organizationId !== "",
  });

export const useProductContext = () => {
  const { user, signOut } = useSession();
  const savedOrganizationId = useWorkspaceSelection((s) => s.organizationId);
  const savedWorkspaceId = useWorkspaceSelection((s) => s.workspaceId);
  const selectOrganization = useWorkspaceSelection((s) => s.selectOrganization);
  const selectWorkspace = useWorkspaceSelection((s) => s.selectWorkspace);

  const organizations = user?.organizations ?? [];
  const selectedOrganization =
    organizations.find(
      (organization) => organization.id === savedOrganizationId,
    ) ?? organizations[0];
  const organizationId = selectedOrganization?.id ?? "";

  const workspaceList = useWorkspaceList(organizationId);
  const workspaces = workspaceList.data?.data ?? [];
  const selectedWorkspace =
    workspaces.find((workspace) => workspace.id === savedWorkspaceId) ??
    workspaces.find((workspace) => workspace.is_default) ??
    workspaces[0];
  const workspaceId = selectedWorkspace?.id ?? "";

  useEffect(() => {
    if (organizationId && organizationId !== savedOrganizationId) {
      selectOrganization(organizationId);
    }
  }, [organizationId, savedOrganizationId, selectOrganization]);

  useEffect(() => {
    if (workspaceId && workspaceId !== savedWorkspaceId) {
      selectWorkspace(workspaceId);
    }
  }, [workspaceId, savedWorkspaceId, selectWorkspace]);

  return {
    user,
    organizationId,
    workspaceId,
    workspaces,
    selectedOrganization,
    selectOrganization,
    selectWorkspace,
    signOut,
  };
};

export const useScopeCreation = () => {
  const queryClient = useQueryClient();
  const selectOrganization = useWorkspaceSelection((s) => s.selectOrganization);
  const selectWorkspace = useWorkspaceSelection((s) => s.selectWorkspace);

  const organizationCreated = (organization: Organization) => {
    selectOrganization(organization.id);
    selectWorkspace(organization.default_workspace_id);

    void queryClient.invalidateQueries({ queryKey: queryKeys.me });
    void queryClient.invalidateQueries({
      queryKey: queryKeys.workspaces(organization.id),
    });
  };

  const workspaceCreated = (workspace: Workspace) => {
    queryClient.setQueryData<components["schemas"]["WorkspaceList"]>(
      queryKeys.workspaces(workspace.organization_id),
      (current) => ({
        data: [
          ...(current?.data.filter((item) => item.id !== workspace.id) ?? []),
          workspace,
        ],
        next_cursor: current?.next_cursor ?? null,
      }),
    );
    selectWorkspace(workspace.id);
  };

  return { organizationCreated, workspaceCreated };
};
