import { LoaderCircle, RefreshCw } from "lucide-react";
import { toast } from "sonner";

import {
  ImportStatusBadge,
  StatusBadge,
} from "@/components/training/status-badge";
import { TableCard } from "@/components/training/training-ui";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useSyncSource } from "@/hooks/use-grad";
import { formatCount, formatDateTime } from "@/lib/grad/format";
import type { ImportJob, Source } from "@/lib/grad/types";

const PROVIDER_LABEL: Record<Source["provider"]["kind"], string> = {
  langfuse: "Langfuse",
  langsmith: "LangSmith",
  braintrust: "Braintrust",
  posthog: "PostHog",
  phoenix: "Phoenix",
  gradiated: "Gradiated traces",
};

export const SourcesTable = ({
  sources,
  canSync,
}: {
  sources: readonly Source[];
  canSync: boolean;
}) => {
  const sync = useSyncSource();

  return (
    <TableCard label="Sources">
      <Table>
        <TableHeader className="bg-muted/40">
          <TableRow className="hover:bg-transparent">
            <TableHead className="h-11 pl-5">Provider</TableHead>
            <TableHead className="h-11">Status</TableHead>
            <TableHead className="h-11">Schedule</TableHead>
            <TableHead className="h-11">Last sync</TableHead>
            <TableHead className="h-11 pr-5 text-right">Sync</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {sources.map((source) => {
            const syncing =
              source.lastSync?.status === "queued" ||
              source.lastSync?.status === "running" ||
              (sync.isPending && sync.variables === source.id);

            return (
              <TableRow key={source.id} className="align-top">
                <TableCell className="py-3 pl-5">
                  <p className="font-medium">
                    {PROVIDER_LABEL[source.provider.kind]}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {[source.provider.project, source.provider.host]
                      .filter(Boolean)
                      .join(" · ") || "Default project"}
                  </p>
                </TableCell>
                <TableCell className="max-w-sm py-3 whitespace-normal">
                  {source.status === "paused" ? (
                    <StatusBadge label="Paused" tone="warning" />
                  ) : source.lastError ? (
                    <StatusBadge label="Failing" tone="danger" />
                  ) : (
                    <StatusBadge label="Active" tone="success" />
                  )}
                  {source.lastError ? (
                    <p className="mt-1.5 text-xs text-destructive">
                      {source.lastError}
                      {source.lastErrorAt
                        ? ` (${formatDateTime(source.lastErrorAt)}, ${source.consecutiveFailures} failed in a row)`
                        : ""}
                    </p>
                  ) : null}
                  {source.pausedReason ? (
                    <p className="mt-1 text-xs text-muted-foreground">
                      {source.pausedReason}
                    </p>
                  ) : null}
                </TableCell>
                <TableCell className="py-3">
                  {source.schedule ? (
                    <>
                      <code className="font-mono text-xs">
                        {source.schedule}
                      </code>
                      {source.nextSyncAt ? (
                        <p className="text-xs text-muted-foreground">
                          Next {formatDateTime(source.nextSyncAt)}
                        </p>
                      ) : null}
                    </>
                  ) : (
                    <span className="text-muted-foreground">On request</span>
                  )}
                </TableCell>
                <TableCell className="py-3">
                  {source.lastSync ? (
                    <div className="space-y-1">
                      <ImportStatusBadge status={source.lastSync.status} />
                      <p className="text-xs text-muted-foreground">
                        {formatDateTime(
                          source.lastSync.finishedAt ??
                            source.lastSync.createdAt,
                        )}
                        {source.lastSync.datasetVersion
                          ? ` · v${source.lastSync.datasetVersion}`
                          : ""}
                      </p>
                    </div>
                  ) : (
                    <span className="text-muted-foreground">Never</span>
                  )}
                </TableCell>
                <TableCell className="py-3 pr-5 text-right">
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={!canSync || syncing}
                    title={
                      canSync
                        ? undefined
                        : "Only workspace admins can sync sources."
                    }
                    onClick={() =>
                      sync.mutate(source.id, {
                        onSuccess: () => toast.success("Sync started"),
                      })
                    }
                  >
                    {syncing ? (
                      <LoaderCircle className="animate-spin" />
                    ) : (
                      <RefreshCw />
                    )}
                    Sync now
                  </Button>
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </TableCard>
  );
};

const CONNECTOR_LABEL: Record<ImportJob["connector"], string> = {
  auto: "Detected",
  grad_trajectories: "grad trajectories",
  openai_chat: "OpenAI chat",
  gradiated: "Gradiated traces",
  otel: "OpenTelemetry",
  langfuse: "Langfuse",
  posthog: "PostHog",
  braintrust: "Braintrust",
  langsmith: "LangSmith",
};

const importOrigin = (job: ImportJob) => {
  const kind = job.source.kind;

  if (kind === "upload") return "File upload";
  if (kind === "hf")
    return `Hugging Face ${String(job.source.repo ?? "")}`.trim();
  if (kind === "benchmark")
    return `Benchmark ${String(job.source.benchmark ?? "")}`.trim();
  if (kind === "source") return "Source sync";

  return CONNECTOR_LABEL[job.connector];
};

export const ImportsTable = ({
  imports,
}: {
  imports: readonly ImportJob[];
}) => (
  <TableCard label="Imports">
    <Table>
      <TableHeader className="bg-muted/40">
        <TableRow className="hover:bg-transparent">
          <TableHead className="h-11 pl-5">Import</TableHead>
          <TableHead className="h-11">Status</TableHead>
          <TableHead className="h-11 text-right">Added</TableHead>
          <TableHead className="h-11 text-right">Dropped</TableHead>
          <TableHead className="h-11">Version</TableHead>
          <TableHead className="h-11 pr-5">Started</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {imports.map((job) => (
          <TableRow key={job.id} className="align-top">
            <TableCell className="py-3 pl-5">
              <p className="font-medium">{importOrigin(job)}</p>
              <p className="text-xs text-muted-foreground">
                {CONNECTOR_LABEL[job.connector]} format
              </p>
            </TableCell>
            <TableCell className="max-w-sm py-3 whitespace-normal">
              <ImportStatusBadge status={job.status} />
              {job.error ? (
                <p className="mt-1.5 text-xs text-destructive">{job.error}</p>
              ) : null}
              {job.dropReasons.length ? (
                <details className="mt-1.5 text-xs text-muted-foreground">
                  <summary className="cursor-pointer">
                    Why rows were dropped
                  </summary>
                  <ul className="mt-1 list-disc space-y-0.5 pl-4">
                    {job.dropReasons.slice(0, 10).map((reason) => (
                      <li key={reason}>{reason}</li>
                    ))}
                  </ul>
                </details>
              ) : null}
            </TableCell>
            <TableCell className="py-3 text-right tabular-nums">
              {formatCount(job.importedCount)}
            </TableCell>
            <TableCell className="py-3 text-right tabular-nums text-muted-foreground">
              {formatCount(job.droppedCount)}
            </TableCell>
            <TableCell className="py-3 tabular-nums">
              {job.datasetVersion ? `v${job.datasetVersion}` : "—"}
            </TableCell>
            <TableCell className="py-3 pr-5 text-muted-foreground">
              {formatDateTime(job.createdAt)}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  </TableCard>
);
