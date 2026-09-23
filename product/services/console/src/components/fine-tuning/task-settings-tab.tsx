import { useMemo } from "react";

import {
  ModelSelect,
  SettingRow,
  SettingsCard,
} from "@/components/fine-tuning/settings-card";
import type { TaskRow } from "@/store/fine-tuning-types";
import { useMockFineTuning } from "@/store/mock-fine-tuning";

export const TaskSettingsTab = ({ task }: { task: TaskRow }) => {
  const models = useMockFineTuning((state) => state.models);
  const traces = useMockFineTuning((state) => state.traces);
  const setTaskBaseModel = useMockFineTuning((state) => state.setTaskBaseModel);
  const setTaskComparisonModel = useMockFineTuning(
    (state) => state.setTaskComparisonModel,
  );

  const trainableBases = useMemo(
    () => models.filter((model) => model.trainable).map((model) => model.id),
    [models],
  );
  const comparisonOptions = useMemo(
    () => [
      ...new Set([
        task.comparison_model_id,
        ...traces
          .filter((row) => row.task === task.slug)
          .map((row) => row.model),
      ]),
    ],
    [traces, task.comparison_model_id, task.slug],
  );

  return (
    <SettingsCard>
      <SettingRow
        title="Comparison model"
        description="New versions are judged, costed and timed against this."
      >
        <ModelSelect
          label="Comparison model"
          value={task.comparison_model_id}
          models={comparisonOptions}
          onChange={(modelId) => setTaskComparisonModel(task.id, modelId)}
        />
      </SettingRow>
      <SettingRow
        title="Base model"
        description="The next version trains on this. Existing versions are unaffected."
      >
        <ModelSelect
          label="Base model"
          value={task.base_model_id}
          models={trainableBases}
          onChange={(modelId) => setTaskBaseModel(task.id, modelId)}
        />
      </SettingRow>
    </SettingsCard>
  );
};
