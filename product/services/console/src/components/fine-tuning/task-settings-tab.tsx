import { useProductContext } from "@/hooks/use-product-context";
import { useOptimisticValue } from "@/hooks/use-optimistic-patch";
import type { components } from "@/api/schema";
import { OptionSelect } from "@/components/option-select";
import {
  COMPARISON_MODELS,
  TRAINING_BASE_MODELS,
} from "@gradiated/contracts/model-catalog";
import { useQuery } from "@tanstack/react-query";
import { modelsQuery } from "@/api/queries";
import { taskSettingsKey, useTrainingMutation } from "@/hooks/use-training";
import { SettingRow, SettingsCard } from "./settings-card";
import { QueryState } from "./query-state";
import type { TaskRow } from "@/store/fine-tuning-types";

export const TaskSettingsTab = ({ task: savedTask }: { task: TaskRow }) => {
  const { workspaceId } = useProductContext();
  const task = useOptimisticValue<TaskRow, components["schemas"]["UpdateTask"]>(
    taskSettingsKey(workspaceId, savedTask.name),
    savedTask,
    (current, patch) => ({ ...current, ...patch }),
  );
  const models = useQuery(modelsQuery());
  const { update, canEdit } = useTrainingMutation(task.name);
  const availableModels = (models.data?.data ?? []).filter((model) =>
    TRAINING_BASE_MODELS.some((base) => base.id === model.id),
  );
  const baseModelOptions = availableModels.map((model) => ({
    value: model.id,
    label: `${model.id}${model.status === "unavailable" ? " (training only)" : ""}`,
    disabled: false,
  }));

  if (
    task.base_model_id &&
    !availableModels.some((model) => model.id === task.base_model_id)
  ) {
    baseModelOptions.unshift({
      value: task.base_model_id,
      label: `${task.base_model_id} (unavailable)`,
      disabled: true,
    });
  }

  const comparisonOptions: {
    value: string;
    label: string;
    disabled: boolean;
  }[] = COMPARISON_MODELS.filter(
    (model) =>
      model.id.startsWith("openai/") ||
      model.id.startsWith("anthropic/") ||
      model.id === "Qwen/Qwen3-0.6B" ||
      models.data?.data.some(
        (hosted) => hosted.id === model.id && hosted.status === "available",
      ),
  ).map((model) => ({ value: model.id, label: model.id, disabled: false }));

  if (
    task.comparison_model_id &&
    !comparisonOptions.some((model) => model.value === task.comparison_model_id)
  ) {
    comparisonOptions.unshift({
      value: task.comparison_model_id,
      label: `${task.comparison_model_id} (unavailable)`,
      disabled: true,
    });
  }

  return (
    <SettingsCard>
      <SettingRow
        title="Comparison model"
        description="New versions are judged, costed and timed against this."
      >
        <OptionSelect
          label="Comparison model"
          className="w-80 font-mono text-xs"
          value={task.comparison_model_id ?? ""}
          placeholder="Select a comparison model"
          disabled={!canEdit || !models.data}
          onValueChange={(comparison_model_id) =>
            update.mutate({ comparison_model_id })
          }
          options={comparisonOptions}
        />
      </SettingRow>
      <SettingRow
        title="Base model"
        description="The next version trains on this. Existing versions are unaffected."
      >
        <div>
          <OptionSelect
            label="Base model"
            className="w-64 font-mono text-xs"
            value={task.base_model_id ?? ""}
            placeholder="Select a base model"
            disabled={!canEdit || !models.data}
            onValueChange={(base_model_id) => update.mutate({ base_model_id })}
            options={baseModelOptions}
          />
          <QueryState query={models} />
        </div>
      </SettingRow>
      {update.error ? (
        <p role="alert" className="p-4 text-sm text-destructive">
          {update.error.message}
        </p>
      ) : null}
    </SettingsCard>
  );
};
