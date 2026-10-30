import { SettingsCard } from "@/components/fine-tuning/settings-card";
import { TraceCaptureSettings } from "@/components/fine-tuning/trace-capture-settings";
import { useProductContext } from "@/hooks/use-product-context";
import { SettingsHeader } from "./settings-layout";

export const WorkspacePrivacySettingsPage = () => {
  const { workspaceId, workspaces } = useProductContext();
  const workspace = workspaces.find((row) => row.id === workspaceId);

  return (
    <>
      <SettingsHeader
        title="Privacy"
        description="Control how content is captured and retained for this workspace."
      />
      {workspace ? (
        <SettingsCard>
          <TraceCaptureSettings />
        </SettingsCard>
      ) : (
        <p role="status">Loading workspace privacy settings…</p>
      )}
    </>
  );
};
