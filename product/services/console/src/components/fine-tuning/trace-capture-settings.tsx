import { useWorkspaceSettings } from "@/hooks/use-workspace-settings";
import { OptionSelect } from "@/components/option-select";
import { Switch } from "@/components/ui/switch";
import { SettingRow } from "./settings-card";

export const TraceCaptureSettings = () => {
  const { workspace, save, canEdit } = useWorkspaceSettings();

  if (!workspace) return null;

  return (
    <>
      <SettingRow
        title="Trace capture"
        description="Stores request and response content for requests that name a task, for training and evaluation. Turn this off to stop storing content; automatic training stops while it is off."
      >
        <Switch
          checked={workspace.trace_capture_enabled}
          disabled={!canEdit}
          onCheckedChange={(trace_capture_enabled) =>
            save.mutate({ trace_capture_enabled })
          }
          aria-label="Trace capture"
        />
      </SettingRow>
      <SettingRow
        title="Content retention"
        description="Applies to new captures. Existing content keeps the retention chosen when it was captured."
      >
        <OptionSelect
          label="Content retention"
          value={String(workspace.trace_retention_days) as "30" | "90" | "180"}
          disabled={!canEdit}
          onValueChange={(days) =>
            save.mutate({ trace_retention_days: Number(days) as 30 | 90 | 180 })
          }
          options={(["30", "90", "180"] as const).map((days) => ({
            value: days,
            label: `${days} days`,
          }))}
        />
      </SettingRow>
      {save.error ? (
        <p role="alert" className="p-4 text-sm text-destructive">
          Could not save capture settings. {save.error.message}
        </p>
      ) : null}
    </>
  );
};
