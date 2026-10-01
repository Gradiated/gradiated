import { useProductContext } from "@/hooks/use-product-context";
import { useOptimisticValue } from "@/hooks/use-optimistic-patch";
import type { components } from "@/api/schema";
import { OptionSelect } from "@/components/option-select";
import { TRAINING_BASE_MODELS } from "@gradiated/contracts/model-catalog";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { modelsQuery } from "@/api/queries";
import { taskSettingsKey, useTrainingMutation } from "@/hooks/use-training";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
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
  const [comparison, setComparison] = useState(task.comparison_model_id ?? "");
  const availableModels = (models.data?.data ?? []).filter(
    (model) =>
      model.status === "available" ||
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

  return (
    <SettingsCard>
      <SettingRow
        title="Comparison model"
        description="New versions are judged, costed and timed against this."
      >
        <form
          className="flex gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            update.mutate({ comparison_model_id: comparison.trim() });
          }}
        >
          <Input
            aria-label="Comparison model"
            value={comparison}
            onChange={(event) => setComparison(event.target.value)}
            disabled={!canEdit || update.isPending}
            required
          />
          <Button
            disabled={
              !canEdit ||
              update.isPending ||
              !comparison.trim() ||
              comparison.trim() === task.comparison_model_id
            }
          >
            Save
          </Button>
        </form>
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
