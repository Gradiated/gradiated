import { create } from "zustand";
import { persist } from "zustand/middleware";

interface WorkspaceSelectionState {
  organizationId: string;
  workspaceId: string;
  selectOrganization: (organizationId: string) => void;
  selectWorkspace: (workspaceId: string) => void;
  reset: () => void;
}

export const useWorkspaceSelection = create<WorkspaceSelectionState>()(
  persist(
    (set) => ({
      organizationId: "",
      workspaceId: "",
      selectOrganization: (organizationId) =>
        set({ organizationId, workspaceId: "" }),
      selectWorkspace: (workspaceId) => set({ workspaceId }),
      reset: () => set({ organizationId: "", workspaceId: "" }),
    }),
    { name: "gradiated-workspace-selection" },
  ),
);
