import { useWorkspaceSettings } from "@/hooks/use-workspace-settings";
import { OptionSelect } from "@/components/option-select";
import { JUDGE_MODELS } from "@gradiated/contracts/model-catalog";
import { SettingRow } from "./settings-card";

export const JudgeSettings = () => {
  const { workspace, save, canEdit } = useWorkspaceSettings();

  if (!workspace) return null;

  return (
    <>
      <SettingRow
        title="Default judge model"
        description="New tasks start with this judge. Change an individual task’s judge in its settings."
      >
        <OptionSelect
          label="Default judge model"
          className="w-64 font-mono text-xs"
          value={workspace.default_judge_model}
          disabled={!canEdit}
          onValueChange={(default_judge_model) =>
            save.mutate({ default_judge_model })
          }
          options={JUDGE_MODELS.map(({ id }) => ({ value: id, label: id }))}
        />
      </SettingRow>
      {save.error ? (
        <p role="alert" className="p-4 text-sm text-destructive">
          {save.error.message}
        </p>
      ) : null}
    </>
  );
};
