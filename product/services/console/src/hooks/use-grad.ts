import { ConflictError, newIdempotencyKey } from "@gradiated/grad";
import {
  keepPreviousData,
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from "@tanstack/react-query";
import { useMemo } from "react";

import {
  createGradSession,
  gradBaseUrl,
  publishArtifactVersion,
  trainingTokenQuery,
  type GradSession,
} from "@/api/grad";
import { useProductContext } from "@/hooks/use-product-context";
import {
  GRAD_API_URL,
  GRAD_KEY,
  gradKeys,
  useTrainingAvailable,
} from "@/lib/grad/config";

export { gradKeys };
import { isTerminalEval, isTerminalRun } from "@/lib/grad/labels";
import type { PlanRunRequest } from "@/lib/grad/types";
import { sha256Hex, uploadHeaders, uploadTarget } from "@/lib/grad/upload";
import type { UsageGroupBy } from "@/lib/grad/usage";

const LIST_LIMIT = 50;
const ACTIVE_POLL_MS = 10_000;

const sessions = new WeakMap<QueryClient, Map<string, GradSession>>();

const sessionFor = (
  queryClient: QueryClient,
  apiUrl: string,
  workspaceId: string,
) => {
  const byWorkspace =
    sessions.get(queryClient) ?? new Map<string, GradSession>();
  sessions.set(queryClient, byWorkspace);

  const existing = byWorkspace.get(workspaceId);
  if (existing) return existing;

  const query = trainingTokenQuery(workspaceId);
  const session = createGradSession({
    baseURL: gradBaseUrl(apiUrl, window.location.origin),
    token: async (renew) =>
      (await queryClient.fetchQuery(renew ? { ...query, staleTime: 0 } : query))
        .token,
  });
  byWorkspace.set(workspaceId, session);

  return session;
};

// No session (so no token and no grad request) unless training is available.
export const useGrad = () => {
  const { workspaceId } = useProductContext();
  const queryClient = useQueryClient();
  const available = useTrainingAvailable() === true;
  const session = useMemo(
    () =>
      available && GRAD_API_URL && workspaceId
        ? sessionFor(queryClient, GRAD_API_URL, workspaceId)
        : undefined,
    [available, queryClient, workspaceId],
  );

  return { workspaceId, session, queryClient };
};

const requireSession = (session: GradSession | undefined) => {
  if (!session) throw new Error("No workspace is selected.");

  return session.grad.api;
};

export const useRuns = () => {
  const { workspaceId, session } = useGrad();

  return useInfiniteQuery({
    queryKey: gradKeys.runs(workspaceId),
    queryFn: ({ pageParam, signal }) =>
      requireSession(session).listRuns(
        { limit: LIST_LIMIT, ...(pageParam ? { cursor: pageParam } : {}) },
        { signal },
      ),
    initialPageParam: "",
    getNextPageParam: (page) => page.nextCursor ?? undefined,
    enabled: Boolean(session),
    refetchInterval: (query) =>
      query.state.data?.pages[0]?.data.some((run) => !isTerminalRun(run.status))
        ? ACTIVE_POLL_MS
        : false,
  });
};

export const useRun = (id: string) => {
  const { workspaceId, session } = useGrad();

  return useQuery({
    queryKey: gradKeys.run(workspaceId, id),
    queryFn: ({ signal }) => requireSession(session).getRun(id, { signal }),
    enabled: Boolean(session && id),
    refetchInterval: (query) =>
      query.state.data && !isTerminalRun(query.state.data.status)
        ? 30_000
        : false,
  });
};

export const useCheckpoints = (runId: string) => {
  const { workspaceId, session } = useGrad();

  return useQuery({
    queryKey: gradKeys.checkpoints(workspaceId, runId),
    queryFn: async ({ signal }) =>
      (
        await requireSession(session).listRunCheckpoints(
          runId,
          { limit: 200 },
          { signal },
        )
      ).data,
    enabled: Boolean(session && runId),
  });
};

export const useArtifact = (id: string | null) => {
  const { workspaceId, session } = useGrad();

  return useQuery({
    queryKey: [...gradKeys.all(workspaceId), "artifact", id],
    queryFn: ({ signal }) =>
      requireSession(session).getArtifact(id ?? "", { signal }),
    enabled: Boolean(session && id),
    staleTime: Infinity,
  });
};

export const useBaseModels = () => {
  const { workspaceId, session } = useGrad();

  return useQuery({
    queryKey: [...gradKeys.all(workspaceId), "base-models"],
    queryFn: async ({ signal }) =>
      (await requireSession(session).listBaseModels({ signal })).data,
    enabled: Boolean(session),
    staleTime: 10 * 60_000,
  });
};

export const useDatasets = () => {
  const { workspaceId, session } = useGrad();

  return useInfiniteQuery({
    queryKey: gradKeys.datasets(workspaceId),
    queryFn: ({ pageParam, signal }) =>
      requireSession(session).listDatasets(
        { limit: LIST_LIMIT, ...(pageParam ? { cursor: pageParam } : {}) },
        { signal },
      ),
    initialPageParam: "",
    getNextPageParam: (page) => page.nextCursor ?? undefined,
    enabled: Boolean(session),
  });
};

export const useDataset = (name: string) => {
  const { workspaceId, session } = useGrad();

  return useQuery({
    queryKey: [...gradKeys.datasets(workspaceId), "detail", name],
    queryFn: ({ signal }) =>
      requireSession(session).getDataset(name, { signal }),
    enabled: Boolean(session && name),
  });
};

export const useDatasetRecords = (
  name: string,
  version: number | undefined,
) => {
  const { workspaceId, session } = useGrad();

  return useInfiniteQuery({
    queryKey: [...gradKeys.datasets(workspaceId), "records", name, version],
    queryFn: ({ pageParam, signal }) =>
      requireSession(session).listDatasetRecords(
        name,
        {
          limit: 20,
          ...(version ? { version } : {}),
          ...(pageParam ? { cursor: pageParam } : {}),
        },
        { signal },
      ),
    initialPageParam: "",
    getNextPageParam: (page) => page.nextCursor ?? undefined,
    enabled: Boolean(session && name && version),
    placeholderData: keepPreviousData,
  });
};

export const useSources = () => {
  const { workspaceId, session } = useGrad();

  return useQuery({
    queryKey: gradKeys.sources(workspaceId),
    queryFn: async ({ signal }) =>
      (await requireSession(session).listSources({ limit: 200 }, { signal }))
        .data,
    enabled: Boolean(session),
    refetchInterval: (query) =>
      query.state.data?.some(
        (source) =>
          source.lastSync?.status === "queued" ||
          source.lastSync?.status === "running",
      )
        ? ACTIVE_POLL_MS
        : false,
  });
};

export const useImports = () => {
  const { workspaceId, session } = useGrad();

  return useQuery({
    queryKey: gradKeys.imports(workspaceId),
    queryFn: async ({ signal }) =>
      (await requireSession(session).listImports({ limit: 200 }, { signal }))
        .data,
    enabled: Boolean(session),
    refetchInterval: (query) =>
      query.state.data?.some(
        (job) => job.status === "queued" || job.status === "running",
      )
        ? ACTIVE_POLL_MS / 2
        : false,
  });
};

export const useEvals = () => {
  const { workspaceId, session } = useGrad();

  return useInfiniteQuery({
    queryKey: gradKeys.evals(workspaceId),
    queryFn: ({ pageParam, signal }) =>
      requireSession(session).listEvals(
        { limit: LIST_LIMIT, ...(pageParam ? { cursor: pageParam } : {}) },
        { signal },
      ),
    initialPageParam: "",
    getNextPageParam: (page) => page.nextCursor ?? undefined,
    enabled: Boolean(session),
    refetchInterval: (query) =>
      query.state.data?.pages[0]?.data.some(
        (evaluation) => !isTerminalEval(evaluation.status),
      )
        ? ACTIVE_POLL_MS
        : false,
  });
};

export const useEval = (id: string) => {
  const { workspaceId, session } = useGrad();

  return useQuery({
    queryKey: [...gradKeys.evals(workspaceId), "detail", id],
    queryFn: ({ signal }) => requireSession(session).getEval(id, { signal }),
    enabled: Boolean(session && id),
    refetchInterval: (query) =>
      query.state.data && !isTerminalEval(query.state.data.status)
        ? ACTIVE_POLL_MS
        : false,
  });
};

export const useEvalFailures = (
  id: string,
  model: string | undefined,
  enabled: boolean,
) => {
  const { workspaceId, session } = useGrad();

  return useQuery({
    queryKey: [...gradKeys.evals(workspaceId), "failures", id, model],
    queryFn: async ({ signal }) =>
      (
        await requireSession(session).listEvalFailures(
          id,
          { limit: 50, ...(model ? { model } : {}) },
          { signal },
        )
      ).data,
    enabled: Boolean(session && id && enabled),
  });
};

export const useUsageSummary = (
  range: { from: string; to: string },
  groupBy: UsageGroupBy,
) => {
  const { workspaceId, session } = useGrad();

  return useQuery({
    queryKey: [...gradKeys.all(workspaceId), "usage", range, groupBy],
    queryFn: ({ signal }) =>
      requireSession(session).getUsageSummary(
        { ...range, groupBy },
        { signal },
      ),
    enabled: Boolean(session),
    placeholderData: keepPreviousData,
  });
};

export const useRunActions = (id: string) => {
  const { workspaceId, session, queryClient } = useGrad();

  const settle = async () => {
    await queryClient.invalidateQueries({
      queryKey: gradKeys.run(workspaceId, id),
    });
    await queryClient.invalidateQueries({
      queryKey: gradKeys.runs(workspaceId),
    });
  };

  const cancel = useMutation({
    mutationKey: GRAD_KEY,
    mutationFn: () => requireSession(session).cancelRun(id),
    meta: { errorMessage: "Could not cancel the run." },
    onSuccess: (run) =>
      queryClient.setQueryData(gradKeys.run(workspaceId, id), run),
    onSettled: settle,
  });

  const resume = useMutation({
    mutationKey: GRAD_KEY,
    mutationFn: (maxCostUsd: number | undefined) =>
      requireSession(session).resumeRun(
        id,
        maxCostUsd === undefined ? {} : { maxCostUsd },
      ),
    meta: { errorMessage: "Could not resume the run." },
    onSuccess: (run) => {
      queryClient.setQueryData(gradKeys.run(workspaceId, id), run);
    },
    onSettled: settle,
  });

  return { cancel, resume };
};

export const usePlanRun = () => {
  const { session } = useGrad();

  return useMutation({
    mutationKey: GRAD_KEY,
    mutationFn: (request: PlanRunRequest) =>
      requireSession(session).planRun(request),
  });
};

export const useCreateRun = () => {
  const { workspaceId, session, queryClient } = useGrad();

  return useMutation({
    mutationKey: GRAD_KEY,
    mutationFn: ({
      request,
      idempotencyKey,
    }: {
      request: PlanRunRequest;
      idempotencyKey: string;
    }) => requireSession(session).createRun(request, { idempotencyKey }),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: gradKeys.runs(workspaceId) }),
  });
};

export const useSyncSource = () => {
  const { workspaceId, session, queryClient } = useGrad();

  return useMutation({
    mutationKey: GRAD_KEY,
    mutationFn: (id: string) => requireSession(session).syncSource(id, {}),
    meta: { errorMessage: "Could not start the sync." },
    onSettled: async () => {
      await queryClient.invalidateQueries({
        queryKey: gradKeys.sources(workspaceId),
      });
      await queryClient.invalidateQueries({
        queryKey: gradKeys.imports(workspaceId),
      });
    },
  });
};

export type ImportStage = "hashing" | "uploading" | "importing";

export const useImportFile = () => {
  const { workspaceId, session, queryClient } = useGrad();

  return useMutation({
    mutationKey: GRAD_KEY,
    mutationFn: async ({
      dataset,
      file,
      onStage,
    }: {
      dataset: string;
      file: File;
      onStage: (stage: ImportStage) => void;
    }) => {
      const api = requireSession(session);
      const baseURL = session?.baseURL ?? "";

      onStage("hashing");
      const sha256 = await sha256Hex(file);

      onStage("uploading");
      const ticket = await api.createUpload({
        purpose: "dataset_import",
        filename: file.name,
        sizeBytes: file.size,
        sha256,
      });
      const put = await fetch(uploadTarget(ticket.url, baseURL), {
        method: ticket.method,
        headers: uploadHeaders(ticket.headers),
        body: file,
      });
      if (!put.ok) throw new Error(`The upload failed (HTTP ${put.status}).`);

      onStage("importing");
      try {
        await api.createDataset({ name: dataset });
      } catch (error) {
        if (!(error instanceof ConflictError)) throw error;
      }

      return api.createDatasetImport(
        dataset,
        { source: { kind: "upload", uploadId: ticket.uploadId } },
        { idempotencyKey: newIdempotencyKey() },
      );
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: gradKeys.datasets(workspaceId),
      });
      await queryClient.invalidateQueries({
        queryKey: gradKeys.imports(workspaceId),
      });
    },
  });
};

export const usePublishArtifact = () => {
  const { workspaceId } = useGrad();

  return useMutation({
    mutationFn: (input: {
      model: string;
      artifactId: string;
      version: string;
    }) =>
      publishArtifactVersion({
        workspaceId,
        ...input,
        idempotencyKey: newIdempotencyKey(),
      }),
  });
};

// The browser downloads the bundle straight from storage (a presigned GET with
// no Authorization header), so large bundles stream to disk.
export const useDownloadArtifact = () => {
  const { session } = useGrad();

  return useMutation({
    mutationKey: GRAD_KEY,
    mutationFn: async (id: string) => {
      const download = await requireSession(session).getArtifactDownloadUrl(id);
      if (!/^https?:$/.test(new URL(download.url).protocol))
        throw new Error("The download URL is not an HTTP URL.");

      const link = document.createElement("a");
      link.href = download.url;
      link.download = download.filename;
      link.rel = "noopener";
      link.click();
    },
    meta: { errorMessage: "Could not download the artifact." },
  });
};
