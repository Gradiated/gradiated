import { useQuery } from "@tanstack/react-query";
import {
  COMPARISON_MODELS,
  modelDisplayName,
} from "@gradiated/contracts/model-catalog";
import { externalModelsQuery, modelsQuery } from "@/api/queries";
import type { Option } from "@/components/option-select";

export const useEvaluationModels = (selected: string | null) => {
  const hosted = useQuery(modelsQuery());
  const external = useQuery(externalModelsQuery());
  const options: Option<string>[] = [
    ...COMPARISON_MODELS.filter(
      (model) =>
        !model.id.startsWith("openai/") &&
        !model.id.startsWith("anthropic/") &&
        (model.id === "Qwen/Qwen3-0.6B" ||
          hosted.data?.data.some(
            (entry) => entry.id === model.id && entry.status === "available",
          )),
    ).map((model) => ({ value: model.id, label: model.displayName })),
    ...(external.data?.data ?? [])
      .filter((model) => model.status === "available")
      .map((model) => ({ value: model.id, label: model.name })),
  ];
  if (selected && !options.some((option) => option.value === selected)) {
    options.unshift({
      value: selected,
      label: modelDisplayName(selected),
      disabled: true,
    });
  }

  return { options, hosted, external };
};
