import { useOptimisticPatch } from "./use-optimistic-patch";
import { isTerminalRunStage } from "@gradiated/contracts/training-stages";
import { useEffect } from "react";
import {
  useInfiniteQuery,
  type InfiniteData,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import {
  startTrainingRun,
  cancelTrainingRun,
  getTask,
  listTasks,
  listTaskRuns,
  listTaskVersions,
  listRunEvents,
  updateTask,
  promoteVersion,
} from "@/api/training";
import type { components } from "@/api/schema";
import { canManageOrganization } from "@/lib/roles";
import { useProductContext } from "./use-product-context";
import { versionsForTask } from "@/store/fine-tuning-views";

export const trainingKey = (workspace: string) =>
  ["training", workspace] as const;

export const useTasks = ({ enabled = true }: { enabled?: boolean } = {}) => {
  const { workspaceId } = useProductContext();

  return useQuery({
    queryKey: [...trainingKey(workspaceId), "tasks"],
    queryFn: ({ signal }) => listTasks(workspaceId, signal),
    enabled: enabled && Boolean(workspaceId),
    staleTime: 300_000,
    refetchInterval: 300_000,
    refetchOnWindowFocus: "always",
  });
};

export const useTask = (task: string) => {
  const { workspaceId } = useProductContext();

  return useQuery({
    queryKey: [...trainingKey(workspaceId), "task", task],
    queryFn: ({ signal }) => getTask(workspaceId, task, signal),
    enabled: Boolean(workspaceId && task),
    staleTime: 300_000,
    refetchInterval: 300_000,
    refetchOnWindowFocus: "always",
  });
};

export const useTaskHistory = (
  task: Pick<components["schemas"]["Task"], "id" | "name">,
) => {
  const { workspaceId } = useProductContext();

  return useQuery({
    queryKey: [...trainingKey(workspaceId), "history", task.id],
    queryFn: async ({ signal }) => {
      const [runs, versions] = await Promise.all([
        listTaskRuns(workspaceId, task.id, signal),
        listTaskVersions(workspaceId, task.name, signal),
      ]);

      return {
        runs: runs.data,
        versions: versionsForTask(versions.data, runs.data),
      };
    },
    enabled: Boolean(workspaceId && task.id),
    staleTime: 300_000,
    refetchOnWindowFocus: "always",
    refetchInterval: (query) =>
      query.state.data?.runs.some((run) => !isTerminalRunStage(run.stage))
        ? 10_000
        : 300_000,
  });
};

export const useRunEvents = (runId: string | undefined) => {
  const { workspaceId } = useProductContext();
  const client = useQueryClient();
  const history = useInfiniteQuery({
    queryKey: [...trainingKey(workspaceId), "events", runId],
    queryFn: ({ pageParam, signal }) =>
      listRunEvents(workspaceId, runId!, pageParam, signal),
    initialPageParam: undefined as number | undefined,
    getNextPageParam: (page) =>
      page.next_cursor === null ? undefined : Number(page.next_cursor),
    enabled: Boolean(workspaceId && runId),
    staleTime: Infinity,
    refetchOnWindowFocus: false,
  });
  const after = history.data?.pages.at(-1)?.data.at(-1)?.id ?? 0;
  const tail = useQuery({
    queryKey: [...trainingKey(workspaceId), "event-tail", runId, after],
    queryFn: ({ signal }) => listRunEvents(workspaceId, runId!, after, signal),
    enabled: Boolean(
      workspaceId && runId && history.data && !history.hasNextPage,
    ),
    refetchInterval: 10_000,
    refetchOnWindowFocus: false,
  });
  useEffect(() => {
    if (!tail.data?.data.length) return;
    client.setQueryData<
      InfiniteData<
        Awaited<ReturnType<typeof listRunEvents>>,
        number | undefined
      >
    >([...trainingKey(workspaceId), "events", runId], (current) => {
      if (!current || (current.pages.at(-1)?.data.at(-1)?.id ?? 0) !== after)
        return current;
      return {
        pages: [...current.pages, tail.data!],
        pageParams: [...current.pageParams, after],
      };
    });
  }, [client, workspaceId, runId, after, tail.data]);

  return { ...history, error: history.error ?? tail.error };
};

export const taskSettingsKey = (workspace: string, task: string) =>
  [...trainingKey(workspace), "settings", task] as const;

export const useTrainingMutation = (task: string) => {
  const { workspaceId, selectedOrganization } = useProductContext();
  const client = useQueryClient();
  const invalidate = () =>
    client.invalidateQueries({ queryKey: trainingKey(workspaceId) });
  const update = useOptimisticPatch({
    mutationKey: taskSettingsKey(workspaceId, task),
    queryKey: trainingKey(workspaceId),
    mutationFn: (body: components["schemas"]["UpdateTask"]) =>
      updateTask(workspaceId, task, body),
    commit: (updated) => {
      client.setQueryData([...trainingKey(workspaceId), "task", task], updated);
      client.setQueryData<components["schemas"]["TaskList"]>(
        [...trainingKey(workspaceId), "tasks"],
        (current) =>
          current && {
            ...current,
            data: current.data.map((row) =>
              row.name === task ? { ...row, ...updated } : row,
            ),
          },
      );
    },
  });
  const promote = useMutation({
    mutationFn: (versionId: string) =>
      promoteVersion(workspaceId, task, versionId),
    onSuccess: invalidate,
  });
  const start = useMutation({
    mutationFn: (taskId: string) => startTrainingRun(workspaceId, taskId),
    onSuccess: invalidate,
  });
  const cancel = useMutation({
    mutationFn: (runId: string) => cancelTrainingRun(workspaceId, runId),
    onSuccess: invalidate,
  });
  const canEdit = canManageOrganization(selectedOrganization);

  return { update, promote, start, cancel, canEdit };
};
