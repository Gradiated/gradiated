import { ModelOption } from "@/components/model-label";
import { useWorkspaceSettings } from "@/hooks/use-workspace-settings";
import { OptionCombobox } from "@/components/option-combobox";
import { useEvaluationModels } from "@/hooks/use-evaluation-models";
import { QueryState } from "./query-state";
import { SettingRow } from "./settings-card";

export const JudgeSettings = () => {
  const { workspace, save, canEdit } = useWorkspaceSettings();

  const models = useEvaluationModels(workspace?.default_judge_model ?? null);

  if (!workspace) return null;

  return (
    <>
      <SettingRow
        title="Default judge model"
        description="New tasks start with this judge. Change an individual task’s judge in its settings."
      >
        <OptionCombobox
          renderOption={ModelOption}
          label="Default judge model"
          className="w-64"
          value={workspace.default_judge_model}
          disabled={!canEdit}
          onValueChange={(default_judge_model) =>
            save.mutate({ default_judge_model })
          }
          options={models.options}
        />
      </SettingRow>
      <QueryState query={models.external} />
      {save.error ? (
        <p role="alert" className="p-4 text-sm text-destructive">
          {save.error.message}
        </p>
      ) : null}
    </>
  );
};
