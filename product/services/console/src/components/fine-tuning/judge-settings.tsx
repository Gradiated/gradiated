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
        title="Judge model"
        description="This is the model used to compare fine-tuned models vs existing models to decide which is better."
      >
        <OptionSelect
          label="Judge model"
          className="w-64 font-mono text-xs"
          value={workspace.evaluation_judge}
          disabled={!canEdit}
          onValueChange={(evaluation_judge) =>
            save.mutate({ evaluation_judge })
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
