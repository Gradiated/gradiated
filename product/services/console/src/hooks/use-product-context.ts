import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { useEffect } from "react";

import { getCurrentUser, listWorkspaces } from "@/api/queries";
import { authClient } from "@/auth";
import { useWorkspaceSelection } from "@/store/workspace-selection";

export const useProductContext = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const selection = useWorkspaceSelection();
  const me = useQuery({
    queryKey: ["me"],
    queryFn: getCurrentUser,
    retry: false,
  });

  useEffect(() => {
    if (me.error && "status" in me.error && me.error.status === 401) {
      void navigate({ to: "/login" });
    }
  }, [me.error, navigate]);

  useEffect(() => {
    if (!selection.organizationId && me.data?.organizations[0]) {
      selection.selectOrganization(me.data.organizations[0].id);
    }
  }, [me.data, selection]);

  const workspaces = useQuery({
    queryKey: ["workspaces", selection.organizationId],
    queryFn: () => listWorkspaces(selection.organizationId),
    enabled: Boolean(selection.organizationId),
  });

  useEffect(() => {
    if (!workspaces.data?.data.length) return;
    const selectedExists = workspaces.data.data.some(
      (workspace) => workspace.id === selection.workspaceId,
    );
    if (!selectedExists) {
      const preferred =
        workspaces.data.data.find((workspace) => workspace.is_default) ??
        workspaces.data.data[0];
      if (preferred) selection.selectWorkspace(preferred.id);
    }
  }, [selection, workspaces.data]);

  const signOut = async () => {
    await authClient.signOut();
    queryClient.clear();
    selection.reset();
    await navigate({ to: "/login" });
  };

  return {
    user: me.data,
    organizationId: selection.organizationId,
    workspaceId: selection.workspaceId,
    workspaces: workspaces.data?.data ?? [],
    selectedOrganization: me.data?.organizations.find(
      (organization) => organization.id === selection.organizationId,
    ),
    selectOrganization: selection.selectOrganization,
    selectWorkspace: selection.selectWorkspace,
    signOut,
  };
};
