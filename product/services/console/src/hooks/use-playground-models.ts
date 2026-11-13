import { useQuery } from "@tanstack/react-query";

import { modelsQuery } from "@/api/queries";
import { useProductContext } from "@/hooks/use-product-context";
import { useTasks } from "@/hooks/use-training";
import { playgroundModels } from "@/lib/playground";

export const usePlaygroundModels = (version?: {
  name: string;
  task: string;
}) => {
  const hosted = useQuery(modelsQuery());
  const tasks = useTasks();
  const organizationSlug = useProductContext().selectedOrganization?.slug;

  return {
    models: playgroundModels(
      hosted.data?.data ?? [],
      organizationSlug ? (tasks.data?.data ?? []) : [],
      organizationSlug ?? "",
      version,
    ),
    hosted,
    settled: hosted.isSuccess && tasks.isSuccess,
  };
};
