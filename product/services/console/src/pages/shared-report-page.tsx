import { VERSION_REPORT_FILE } from "@gradiated/contracts";
import { useQuery } from "@tanstack/react-query";
import { useParams } from "@tanstack/react-router";
import { FileText } from "lucide-react";
import { useEffect, useMemo } from "react";

import {
  getSharedReport,
  getSharedReportFileContent,
  getSharedReportFileDownload,
} from "@/api/training";
import {
  parseReport,
  type ParsedReport,
} from "@/components/report/report-schema";
import {
  TrainingReport,
  type ReportFile,
  type ReportSource,
} from "@/components/report/training-report";
import { AdapterExplorerButton } from "@/components/adapter-explorer/explorer-dialog";
import { loadAnonymousFlags, useFeatureFlag } from "@/lib/feature-flags";
import { Skeleton } from "@/components/ui/skeleton";
import { ReportContents, VersionFacts } from "@/components/report/version-rail";
import { httpStatus } from "@/lib/errors";

const GRADIATED_URL = "https://gradiated.com";

type ReportSummary = {
  task: string;
  version: string;
  baseModelId: string;
  createdAt: string;
};

const reportTitle = (
  report: ParsedReport | null | undefined,
  summary: ReportSummary,
) => report?.title ?? `${summary.task} ${summary.version}`;

const ReportSignature = () => (
  <div className="mt-6 flex flex-col items-center gap-3 border-t pt-8 pb-4 text-center">
    <img
      src="/brand/gradiated-full.svg"
      alt="Gradiated"
      width="1258"
      height="288"
      className="h-6 w-auto"
    />
    <p className="max-w-md text-xs leading-5 text-muted-foreground">
      Prepared with Gradiated. Run and train open models at{" "}
      <a href={GRADIATED_URL} className="underline underline-offset-4">
        gradiated.com
      </a>
      .
    </p>
  </div>
);

// React hoists these into <head>.
const PageHead = ({ title }: { title: string }) => (
  <>
    <title>{`${title} · Gradiated`}</title>
    <meta name="robots" content="noindex, nofollow, noarchive" />
    <meta name="referrer" content="no-referrer" />
  </>
);

const Shell = ({ children }: { children: React.ReactNode }) => (
  <div className="min-h-svh bg-background">
    <header className="border-b bg-card/60">
      <div className="mx-auto flex h-14 max-w-6xl items-center gap-4 px-6">
        <a href={GRADIATED_URL} aria-label="Gradiated">
          <img
            src="/brand/gradiated-full.svg"
            alt="Gradiated"
            width="1258"
            height="288"
            className="h-5 w-auto"
          />
        </a>
      </div>
    </header>
    <main className="mx-auto flex max-w-6xl flex-col gap-8 px-6 py-10">
      {children}
    </main>
  </div>
);

export const SharedReportPage = () => {
  const { versionId, signature } = useParams({
    from: "/share/$versionId/$signature",
  });
  useEffect(loadAnonymousFlags, []);
  const exploreWeights = useFeatureFlag("explore-weights");
  const link = useMemo(
    () => ({ version_id: versionId, signature }),
    [versionId, signature],
  );
  const shared = useQuery({
    queryKey: ["shared-report", versionId, signature],
    queryFn: ({ signal }) => getSharedReport(link, signal),
    retry: false,
    staleTime: Infinity,
  });
  const reportFile = shared.data?.files.find(
    (file) => file.name === VERSION_REPORT_FILE,
  );
  const report = useQuery({
    queryKey: ["shared-report", versionId, signature, "report", reportFile?.id],
    queryFn: async ({ signal }) =>
      parseReport(
        (await getSharedReportFileContent(link, reportFile!.id, signal))
          .content,
      ),
    enabled: Boolean(reportFile),
    staleTime: Infinity,
  });
  const source = useMemo<ReportSource>(
    () => ({
      files: shared.data?.files ?? [],
      queryKey: ["shared-report", versionId, signature, "files"],
      readText: async (file: ReportFile) =>
        (await getSharedReportFileContent(link, file.id)).content,
      downloadUrl: async (file: ReportFile) =>
        (await getSharedReportFileDownload(link, file.id)).url,
    }),
    [shared.data, link, versionId, signature],
  );

  if (shared.isPending || (reportFile && report.isPending))
    return (
      <Shell>
        <PageHead title="Model report" />
        <Skeleton className="h-10 w-2/3" />
        <Skeleton className="h-64 w-full" />
      </Shell>
    );

  if (shared.isError || report.isError)
    return (
      <Shell>
        <PageHead title="Report unavailable" />
        <div className="grid min-h-64 place-items-center rounded-xl border border-dashed p-8 text-center">
          <div className="flex max-w-sm flex-col items-center gap-2">
            <FileText className="size-6 text-muted-foreground" />
            <p className="font-medium">
              {httpStatus(shared.error) === 404
                ? "This report link is no longer available"
                : "The report could not be loaded"}
            </p>
            <p className="text-sm text-muted-foreground">
              {httpStatus(shared.error) === 404
                ? "Ask the person who shared it for a new link."
                : "Try again in a moment."}
            </p>
          </div>
        </div>
      </Shell>
    );

  const summary: ReportSummary = {
    task: shared.data.task,
    version: shared.data.version,
    baseModelId: shared.data.base_model_id,
    createdAt: shared.data.created_at,
  };
  const title = reportTitle(report.data, summary);

  return (
    <Shell>
      <PageHead title={title} />
      <div className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        <p className="text-sm text-muted-foreground">
          {summary.task} · {summary.version} · Delivered{" "}
          {new Date(summary.createdAt).toLocaleDateString(undefined, {
            dateStyle: "medium",
          })}
        </p>
      </div>
      <div className="flex flex-wrap items-start gap-10">
        <div className="min-w-0 flex-[999_1_32rem]">
          {report.data ? (
            <TrainingReport report={report.data} source={source} />
          ) : (
            <div className="grid min-h-64 place-items-center rounded-xl border border-dashed p-8 text-center">
              <p className="text-sm text-muted-foreground">
                This version has no report yet.
              </p>
            </div>
          )}
        </div>
        <aside
          aria-label="Version"
          className="flex w-full flex-col lg:sticky lg:top-6 lg:w-72 lg:flex-none [&>section:first-child]:border-t-0 [&>section:first-child]:pt-0"
        >
          {exploreWeights === true ? (
            <AdapterExplorerButton
              target={{ kind: "shared", versionId, signature }}
              title={`${summary.task}/${summary.version}`}
              baseModelId={summary.baseModelId}
            />
          ) : null}
          <ReportContents headings={report.data?.headings} />
          <VersionFacts
            baseModelId={summary.baseModelId}
            checkpoint={shared.data.adapter.checkpoint}
            rank={shared.data.adapter.rank}
            sizeBytes={shared.data.adapter.size_bytes}
          />
        </aside>
      </div>
      <ReportSignature />
    </Shell>
  );
};
