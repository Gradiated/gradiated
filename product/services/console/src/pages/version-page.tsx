import { AdapterExplorerButton } from "@/components/adapter-explorer/explorer-dialog";
import { useFeatureFlag } from "@/lib/feature-flags";
import { WorkloadBenchmarkCard } from "@/components/fine-tuning/workload-benchmark";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Link,
  useNavigate,
  useParams,
  useSearch,
} from "@tanstack/react-router";
import {
  ArrowLeft,
  Check,
  CircleArrowUp,
  Download,
  FileText,
  MessageSquare,
  Plus,
  Trash2,
  TriangleAlert,
} from "lucide-react";
import { useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import {
  completeVersionFile,
  createVersionFile,
  deleteVersionFile,
  getVersionFileContent,
  getVersionFileDownload,
  listVersionFiles,
} from "@/api/training";
import {
  VersionActionDialog,
  type VersionAction,
} from "@/components/fine-tuning/version-actions";
import { parseReport } from "@/components/report/report-schema";
import { ShareMenu } from "@/components/report/share-menu";
import {
  RailSection,
  ReportContents,
  VersionFacts,
} from "@/components/report/version-rail";
import {
  TrainingReport,
  type ReportFile,
  type ReportSource,
} from "@/components/report/training-report";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useProductContext } from "@/hooks/use-product-context";
import {
  trainingKey,
  useTask,
  useTaskHistory,
  useTrainingMutation,
} from "@/hooks/use-training";
import { errorMessage } from "@/lib/errors";
import { formatFileSize } from "@/lib/format";
import { usePrivateModelName } from "@/hooks/use-private-model-name";
import { ConsolePage, LoadFailed } from "@/pages/console-page";
import type { TaskRow, VersionView } from "@/store/fine-tuning-types";
import { VERSION_REPORT_FILE } from "@gradiated/contracts";

const versionStatus = (version: VersionView, current: string) =>
  version.is_production
    ? "In production"
    : version.id === current
      ? "Viewing"
      : version.status === "available"
        ? "Ready"
        : "Not servable yet";

export const VersionPage = () => {
  const { taskId, versionId } = useParams({
    from: "/tasks/$taskId/versions/$versionId",
  });
  const task = useTask(taskId);

  if (task.isPending)
    return (
      <ConsolePage page="tasks" title="Loading version">
        <Skeleton className="h-96 w-full" />
      </ConsolePage>
    );

  if (task.isError)
    return (
      <ConsolePage page="tasks" title="Version">
        <LoadFailed
          subject="model"
          retrying={task.isFetching}
          onRetry={() => void task.refetch()}
        />
      </ConsolePage>
    );

  if (!task.data)
    return (
      <ConsolePage page="tasks" title="Model not found">
        <Link to="/tasks" className="text-sm text-muted-foreground underline">
          Back to models
        </Link>
      </ConsolePage>
    );

  return <VersionView task={task.data} versionId={versionId} />;
};

const VersionView = ({
  task,
  versionId,
}: {
  task: TaskRow;
  versionId: string;
}) => {
  const history = useTaskHistory(task);
  const versions = history.data?.versions ?? [];
  const version = versions.find((candidate) => candidate.id === versionId);

  if (history.isPending)
    return (
      <ConsolePage page="tasks" title="Loading version">
        <Skeleton className="h-96 w-full" />
      </ConsolePage>
    );

  if (history.isError)
    return (
      <ConsolePage page="tasks" title="Version">
        <LoadFailed
          subject="version"
          retrying={history.isFetching}
          onRetry={() => void history.refetch()}
        />
      </ConsolePage>
    );

  if (!version)
    return (
      <ConsolePage page="tasks" title="Version not found">
        <Link
          to="/tasks/$taskId"
          params={{ taskId: task.name }}
          className="text-sm text-muted-foreground underline"
        >
          Back to {task.name}
        </Link>
      </ConsolePage>
    );

  return <VersionReport task={task} version={version} versions={versions} />;
};

const VersionReport = ({
  task,
  version,
  versions,
}: {
  task: TaskRow;
  version: VersionView;
  versions: VersionView[];
}) => {
  const openCase = useSearch({ from: "/tasks/$taskId/versions/$versionId" });
  const navigate = useNavigate({ from: "/tasks/$taskId/versions/$versionId" });

  const exploreWeights = useFeatureFlag("explore-weights");
  const modelName = usePrivateModelName();
  const { workspaceId, user } = useProductContext();
  const { canEdit } = useTrainingMutation(task.name);
  const client = useQueryClient();
  const [action, setAction] = useState<VersionAction | null>(null);
  const picker = useRef<HTMLInputElement>(null);
  const canManageFiles = Boolean(
    canEdit &&
    ((user?.is_staff && user.email_verified) || user?.impersonated_by),
  );
  const path = {
    workspace_id: workspaceId,
    task: task.name,
    version_id: version.id,
  };
  const filesKey = [...trainingKey(workspaceId), "files", version.id];
  const files = useQuery({
    queryKey: filesKey,
    queryFn: ({ signal }) => listVersionFiles(path, signal),
    enabled: Boolean(workspaceId),
  });
  const reportFile = files.data?.data.find(
    (file) => file.name === VERSION_REPORT_FILE,
  );
  const report = useQuery({
    queryKey: [...filesKey, "report", reportFile?.id],
    queryFn: async ({ signal }) =>
      parseReport(
        (
          await getVersionFileContent(
            { ...path, file_id: reportFile!.id },
            signal,
          )
        ).content,
      ),
    enabled: Boolean(reportFile),
    staleTime: Infinity,
  });
  const source = useMemo<ReportSource>(
    () => ({
      files: files.data?.data ?? [],
      queryKey: filesKey,
      readText: async (file: ReportFile) =>
        (await getVersionFileContent({ ...path, file_id: file.id })).content,
      downloadUrl: async (file: ReportFile) =>
        (await getVersionFileDownload({ ...path, file_id: file.id })).url,
    }),
    [files.data, workspaceId, task.name, version.id],
  );

  const download = useMutation({
    mutationFn: (file: ReportFile) =>
      getVersionFileDownload({ ...path, file_id: file.id }),
    onSuccess: ({ url }) => {
      const link = document.createElement("a");
      link.href = url;
      link.referrerPolicy = "no-referrer";
      document.body.append(link);
      link.click();
      link.remove();
    },
    onError: (error) =>
      toast.error(errorMessage(error, "The file could not be downloaded.")),
  });
  const upload = useMutation({
    mutationFn: async (selected: File[]) => {
      for (const file of selected) {
        const grant = await createVersionFile(path, {
          name: file.name,
          size_bytes: file.size,
          content_type: file.type || "application/octet-stream",
        });
        const response = await fetch(grant.upload_url, {
          method: "PUT",
          body: file,
          credentials: "omit",
        });
        if (!response.ok)
          throw new Error(`${file.name} could not be uploaded.`);

        await completeVersionFile({ ...path, file_id: grant.id });
      }
    },
    onSuccess: (_, selected) =>
      toast.success(
        selected.length === 1
          ? `${selected[0]!.name} added.`
          : `${selected.length} files added.`,
      ),
    onError: (error) =>
      toast.error(errorMessage(error, "The files could not be uploaded.")),
    onSettled: () => client.invalidateQueries({ queryKey: filesKey }),
  });
  const remove = useMutation({
    mutationFn: (file: ReportFile) =>
      deleteVersionFile({ ...path, file_id: file.id }),
    onSuccess: (_, file) => toast.success(`${file.name} removed.`),
    onError: (error) =>
      toast.error(errorMessage(error, "The file could not be removed.")),
    onSettled: () => client.invalidateQueries({ queryKey: filesKey }),
  });

  const servable = version.status === "available";
  const promoteBlocked = !canEdit
    ? "Only organization admins can promote a version."
    : !servable
      ? "This version is not servable yet."
      : undefined;

  return (
    <ConsolePage
      page="tasks"
      title={version.name}
      width="wide"
      description={`${report.data?.title ? `${report.data.title} · ` : ""}Delivered ${new Date(
        version.created_at,
      ).toLocaleDateString(undefined, { dateStyle: "medium" })}`}
      back={
        <Link
          to="/tasks/$taskId"
          params={{ taskId: task.name }}
          className="mb-4 inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="size-3.5" />
          {task.name}
        </Link>
      }
    >
      <WorkloadBenchmarkCard task={task.name} versionId={version.id} />
      <div className="flex flex-wrap items-start gap-10">
        <div className="min-w-0 flex-[999_1_32rem]">
          {files.isPending || (reportFile && report.isPending) ? (
            <div className="flex flex-col gap-4">
              <Skeleton className="h-24 w-full" />
              <Skeleton className="h-64 w-full" />
            </div>
          ) : files.isError ? (
            <LoadFailed
              subject="version files"
              retrying={files.isFetching}
              onRetry={() => void files.refetch()}
            />
          ) : report.isError ? (
            <LoadFailed
              subject="report"
              retrying={report.isFetching}
              onRetry={() => void report.refetch()}
            />
          ) : report.data ? (
            <div className="flex flex-col gap-4">
              {canManageFiles && report.data.errors.length ? (
                <div className="flex gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3.5 text-amber-950">
                  <TriangleAlert
                    aria-hidden
                    className="mt-0.5 size-4 shrink-0 text-amber-700"
                  />
                  <div className="flex min-w-0 flex-col gap-2">
                    <p className="text-sm font-medium">
                      report.md has {report.data.errors.length}{" "}
                      {report.data.errors.length === 1 ? "problem" : "problems"}
                      <span className="font-normal text-amber-900/70">
                        {" "}
                        · only staff see this
                      </span>
                    </p>
                    <ul className="flex flex-col gap-1.5 text-xs">
                      {report.data.errors.map((error, index) => (
                        <li key={index} className="flex items-baseline gap-2">
                          <span className="shrink-0 rounded bg-amber-100 px-1.5 py-0.5 font-mono text-[11px] text-amber-900">
                            Line {(error.lines[0] ?? 0) + 1}
                          </span>
                          <span className="min-w-0">{error.error.message}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              ) : null}
              <TrainingReport
                report={report.data}
                source={source}
                openCase={openCase}
                onOpenCase={(next) =>
                  void navigate({
                    search: next,
                    replace: Boolean(openCase.case),
                  })
                }
              />
            </div>
          ) : (
            <div className="grid min-h-64 place-items-center rounded-xl border border-dashed p-8 text-center">
              <div className="flex max-w-sm flex-col items-center gap-2">
                <FileText className="size-6 text-muted-foreground" />
                <p className="font-medium">No report for this version yet</p>
                <p className="text-sm text-muted-foreground">
                  {report.isError
                    ? "The report could not be loaded."
                    : canManageFiles
                      ? "Add a report.md file to show the training report here."
                      : "The Gradiated team will add a training report here."}
                </p>
              </div>
            </div>
          )}
        </div>

        <aside
          aria-label="Version"
          className="flex w-full flex-col lg:sticky lg:top-6 lg:w-72 lg:flex-none"
        >
          <div className="flex flex-col gap-2 pb-5">
            {servable ? (
              <Button asChild>
                <Link
                  to="/playground"
                  search={{
                    model: modelName(task.name, version.name),
                    task: task.name,
                  }}
                >
                  <MessageSquare className="size-4" />
                  Try in playground
                </Link>
              </Button>
            ) : (
              <Button disabled title="This version is not servable yet.">
                <MessageSquare className="size-4" />
                Try in playground
              </Button>
            )}
            {version.is_production ? (
              <Button variant="outline" disabled>
                <Check className="size-4" />
                Promoted
              </Button>
            ) : (
              <Button
                variant="outline"
                disabled={Boolean(promoteBlocked)}
                title={promoteBlocked}
                onClick={() =>
                  setAction({ kind: "promote", versionId: version.id })
                }
              >
                <CircleArrowUp className="size-4" />
                Promote
              </Button>
            )}
            <Button
              variant="outline"
              onClick={() =>
                setAction({ kind: "download", versionId: version.id })
              }
            >
              <Download className="size-4" />
              Download
            </Button>
            {exploreWeights === true ? (
              <AdapterExplorerButton
                target={{
                  workspaceId,
                  task: task.name,
                  versionId: version.id,
                  baseModelId: version.base_model_id,
                }}
                title={`${task.name}/${version.name}`}
                baseModelId={version.base_model_id}
              />
            ) : null}
            <ShareMenu
              path={path}
              queryKey={[...trainingKey(workspaceId), "share", version.id]}
            />
          </div>

          <ReportContents headings={report.data?.headings} />

          <VersionFacts
            baseModelId={version.base_model_id}
            checkpoint={
              version.adapter.validated_base_model_revision ??
              version.adapter.base_model_revision
            }
            rank={version.adapter.rank}
            sizeBytes={version.adapter.size_bytes}
          />

          {files.data?.data.length || canManageFiles ? (
            <RailSection
              title="Files"
              aside={
                canManageFiles ? (
                  <>
                    <input
                      ref={picker}
                      type="file"
                      multiple
                      aria-label="Add files"
                      className="sr-only"
                      onChange={(event) => {
                        const selected = Array.from(event.target.files ?? []);
                        event.target.value = "";
                        if (selected.length) upload.mutate(selected);
                      }}
                    />
                    <Button
                      variant="ghost"
                      size="xs"
                      disabled={upload.isPending}
                      onClick={() => picker.current?.click()}
                    >
                      <Plus />
                      {upload.isPending ? "Uploading…" : "Add files"}
                    </Button>
                  </>
                ) : null
              }
            >
              <ul className="flex flex-col gap-1.5">
                {files.data?.data.map((file) => (
                  <li key={file.id} className="flex items-center gap-2">
                    <span className="flex min-w-0 flex-1 flex-col">
                      <span className="truncate font-mono text-xs">
                        {file.name}
                      </span>
                      <span className="text-xs text-muted-foreground">
                        {formatFileSize(file.size_bytes)}
                      </span>
                    </span>
                    {canManageFiles ? (
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        aria-label={`Remove ${file.name}`}
                        disabled={remove.isPending}
                        onClick={() => remove.mutate(file)}
                      >
                        <Trash2 />
                      </Button>
                    ) : null}
                    <Button
                      variant="outline"
                      size="icon-sm"
                      aria-label={`Download ${file.name}`}
                      disabled={download.isPending}
                      onClick={() => download.mutate(file)}
                    >
                      <Download />
                    </Button>
                  </li>
                ))}
                {!files.data?.data.length ? (
                  <li className="text-sm text-muted-foreground">
                    No files yet.
                  </li>
                ) : null}
              </ul>
            </RailSection>
          ) : null}

          <RailSection title="Versions">
            <ul className="flex flex-col gap-2">
              {versions.map((candidate) => (
                <li key={candidate.id}>
                  <Link
                    to="/tasks/$taskId/versions/$versionId"
                    params={{ taskId: task.name, versionId: candidate.id }}
                    aria-current={
                      candidate.id === version.id ? "page" : undefined
                    }
                    className="flex items-center gap-2.5 text-sm hover:text-foreground"
                  >
                    <span
                      aria-hidden
                      className={`size-2 shrink-0 rounded-full ${
                        candidate.is_production
                          ? "bg-[#3f6d8f]"
                          : candidate.id === version.id
                            ? "bg-[#6e7f31]"
                            : "bg-muted-foreground/30"
                      }`}
                    />
                    <span
                      className={`min-w-0 flex-1 truncate ${candidate.id === version.id ? "font-semibold" : ""}`}
                    >
                      {candidate.name}
                    </span>
                    <span className="shrink-0 text-xs text-muted-foreground">
                      {versionStatus(candidate, version.id)}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          </RailSection>
        </aside>
      </div>
      {action ? (
        <VersionActionDialog
          task={task}
          action={action}
          onClose={() => setAction(null)}
        />
      ) : null}
    </ConsolePage>
  );
};
