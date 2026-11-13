import { useQuery } from "@tanstack/react-query";

import { modelsQuery } from "@/api/queries";
import { useProductContext } from "@/hooks/use-product-context";
import { useTasks } from "@/hooks/use-training";
import { useFeatureFlag } from "@/lib/feature-flags";
import { playgroundModels } from "@/lib/playground";

export const usePlaygroundModels = (version?: {
  name: string;
  task: string;
}) => {
  const training = useFeatureFlag("training") === true;
  const hosted = useQuery(modelsQuery());
  const tasks = useTasks({ enabled: training });
  const organizationSlug = useProductContext().selectedOrganization?.slug;

  return {
    models: playgroundModels(
      hosted.data?.data ?? [],
      training && organizationSlug ? (tasks.data?.data ?? []) : [],
      organizationSlug ?? "",
      version,
    ),
    hosted,
    settled: hosted.isSuccess && (!training || tasks.isSuccess),
  };
};
