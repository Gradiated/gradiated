import type { UpdateWorkspace } from "@/api/queries";

export const workspaceSettingsKey = (organization: string) =>
  ["workspace-settings", organization] as const;

export type WorkspaceSettingsPatch = { id: string; patch: UpdateWorkspace };
