import { useQuery } from "@tanstack/react-query";

import { modelsQuery } from "@/api/queries";
import { useTasks } from "@/hooks/use-training";
import { useFeatureFlag } from "@/lib/feature-flags";
import { playgroundModels } from "@/lib/playground";

export const usePlaygroundModels = () => {
  const training = useFeatureFlag("training") === true;
  const hosted = useQuery(modelsQuery());
  const tasks = useTasks({ enabled: training });

  return {
    models: playgroundModels(
      hosted.data?.data ?? [],
      training ? (tasks.data?.data ?? []) : [],
    ),
    hosted,
    settled: hosted.isSuccess && (!training || tasks.isSuccess),
  };
};
