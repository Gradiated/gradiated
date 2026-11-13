import { useQuery } from "@tanstack/react-query";
import {
  WORKLOAD_BENCHMARK_FILE,
  WorkloadBenchmarkSchema,
} from "@gradiated/contracts";
import { getVersionFileContent, listVersionFiles } from "@/api/training";
import { useProductContext } from "./use-product-context";
import { trainingKey } from "./use-training";

export const useWorkloadBenchmark = (task: string, versionId?: string) => {
  const { workspaceId } = useProductContext();
  const path = { workspace_id: workspaceId, task, version_id: versionId! };
  const filesKey = [...trainingKey(workspaceId), "files", versionId];
  const files = useQuery({
    queryKey: filesKey,
    queryFn: ({ signal }) => listVersionFiles(path, signal),
    enabled: Boolean(workspaceId && versionId),
  });
  const file = files.data?.data.find(
    (item) => item.name === WORKLOAD_BENCHMARK_FILE,
  );
  const query = useQuery({
    queryKey: [...filesKey, "benchmark", file?.id, file?.created_at],
    retry: (count, error) =>
      !(error instanceof SyntaxError || error.name === "ZodError") && count < 3,
    queryFn: async ({ signal }) =>
      WorkloadBenchmarkSchema.parse(
        JSON.parse(
          (await getVersionFileContent({ ...path, file_id: file!.id }, signal))
            .content,
        ),
      ),
    enabled: Boolean(file),
  });

  // A file that exists but does not parse can only be fixed by replacing it,
  // so the editor stays available; retrying a transport error is not enough.
  const invalid =
    !files.error &&
    (query.error instanceof SyntaxError || query.error?.name === "ZodError");

  return {
    ...query,
    invalid,
    isFetching: files.isFetching || query.isFetching,
    retry: () => (files.error || !file ? files.refetch() : query.refetch()),
    error: files.error ?? query.error,
    path,
    filesKey,
    file,
  };
};
