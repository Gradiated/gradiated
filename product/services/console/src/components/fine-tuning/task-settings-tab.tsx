import { ModelOption, modelOption } from "@/components/model-label";
import { useState } from "react";
import { TaskTrainingScheduleSchema } from "@gradiated/contracts";
import { Button } from "@/components/ui/button";
import { NextTraining } from "./next-training";
import { TrainingScheduleEditor } from "./training-schedule-editor";
import { useProductContext } from "@/hooks/use-product-context";
import { useOptimisticValue } from "@/hooks/use-optimistic-patch";
import type { components } from "@/api/schema";
import { OptionSelect } from "@/components/option-select";
import {
  modelDisplayName,
  COMPARISON_MODELS,
  JUDGE_MODELS,
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
  const [scheduleDraft, setScheduleDraft] = useState<string | null>(null);
  const schedule = scheduleDraft ?? task.training_schedule ?? "";
  const validSchedule = TaskTrainingScheduleSchema.safeParse(
    schedule.trim() || null,
  );
  const models = useQuery(modelsQuery());
  const { update, canEdit } = useTrainingMutation(task.name);
  const availableModels = (models.data?.data ?? []).filter((model) =>
    TRAINING_BASE_MODELS.some((base) => base.id === model.id),
  );
  const baseModelOptions = availableModels.map((model) => ({
    ...modelOption(model.id),
    disabled: false,
  }));

  if (
    task.base_model_id &&
    !availableModels.some((model) => model.id === task.base_model_id)
  ) {
    baseModelOptions.unshift({
      value: task.base_model_id,
      label: `${modelDisplayName(task.base_model_id)} (unavailable)`,
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
  ).map((model) => ({ ...modelOption(model.id), disabled: false }));

  if (
    task.comparison_model_id &&
    !comparisonOptions.some((model) => model.value === task.comparison_model_id)
  ) {
    comparisonOptions.unshift({
      value: task.comparison_model_id,
      label: `${modelDisplayName(task.comparison_model_id)} (unavailable)`,
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
          renderOption={ModelOption}
          label="Comparison model"
          className="w-64"
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
            renderOption={ModelOption}
            label="Base model"
            className="w-64"
            value={task.base_model_id ?? ""}
            placeholder="Select a base model"
            disabled={!canEdit || !models.data}
            onValueChange={(base_model_id) => update.mutate({ base_model_id })}
            options={baseModelOptions}
          />
          <QueryState query={models} />
        </div>
      </SettingRow>
      <SettingRow
        title="Judge model"
        description="Judges comparisons for the next training run. Existing results are unaffected."
      >
        <OptionSelect
          renderOption={ModelOption}
          label="Judge model"
          className="w-64"
          value={task.judge_model_id}
          disabled={!canEdit}
          onValueChange={(judge_model_id) => update.mutate({ judge_model_id })}
          options={JUDGE_MODELS.map(({ id }) => modelOption(id))}
        />
      </SettingRow>
      <div className="p-5">
        <p className="text-sm font-medium">Automatic training</p>
        <p className="mt-1 text-xs leading-5 text-muted-foreground">
          Choose when this task trains. All schedule times are in UTC.
        </p>
        <form
          className="mt-4 space-y-3"
          onSubmit={(event) => {
            event.preventDefault();
            if (validSchedule.success)
              update.mutate(
                { training_schedule: validSchedule.data },
                { onSuccess: () => setScheduleDraft(null) },
              );
          }}
        >
          <TrainingScheduleEditor
            value={schedule}
            onChange={setScheduleDraft}
            disabled={!canEdit || update.isPending}
          />
          {!validSchedule.success ? (
            <p role="alert" className="text-xs text-destructive">
              Enter a valid five-field cron schedule.
            </p>
          ) : null}
          {validSchedule.success && validSchedule.data ? (
            <NextTraining schedule={validSchedule.data} />
          ) : null}
          <Button
            size="sm"
            disabled={
              !canEdit ||
              update.isPending ||
              !validSchedule.success ||
              (schedule === (task.training_schedule ?? "") && !update.error)
            }
          >
            Save schedule
          </Button>
        </form>
      </div>
      {update.error ? (
        <p role="alert" className="p-4 text-sm text-destructive">
          {update.error.message}
        </p>
      ) : null}
    </SettingsCard>
  );
};
