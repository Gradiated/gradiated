import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { modelsQuery } from "@/api/queries";
import { useTrainingMutation } from "@/hooks/use-training";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { SettingRow, SettingsCard } from "./settings-card";
import { QueryState } from "./query-state";
import type { TaskRow } from "@/store/fine-tuning-types";

export const TaskSettingsTab = ({ task }: { task: TaskRow }) => {
  const models = useQuery(modelsQuery());
  const { update, canEdit } = useTrainingMutation(task.name);
  const [comparison, setComparison] = useState(task.comparison_model_id ?? "");

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
          <select
            aria-label="Base model"
            className="w-64 rounded-md border bg-background p-2 font-mono text-xs"
            value={task.base_model_id ?? ""}
            disabled={!canEdit || update.isPending || !models.data}
            onChange={(event) =>
              update.mutate({ base_model_id: event.target.value })
            }
          >
            <option value="" disabled>
              Select a base model
            </option>
            {task.base_model_id &&
            !models.data?.data.some(
              (model) =>
                model.id === task.base_model_id && model.status === "available",
            ) ? (
              <option value={task.base_model_id} disabled>
                {task.base_model_id} (unavailable)
              </option>
            ) : null}
            {models.data?.data
              .filter((model) => model.status === "available")
              .map((model) => (
                <option key={model.id} value={model.id}>
                  {model.id}
                </option>
              ))}
          </select>
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
