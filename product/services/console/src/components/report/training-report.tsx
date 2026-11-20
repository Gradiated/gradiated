import Markdoc from "@markdoc/markdoc";
import { useQueries, useQuery } from "@tanstack/react-query";
import * as React from "react";
import {
  createContext,
  createElement,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { parseEval } from "@/lib/eval-data";
import { parseReportData } from "@/lib/report-data";
import {
  EvalBreakdown,
  EvalCaseGrid,
  EvalCases,
  EvalExamples,
  EvalHeadToHead,
  EvalSummary,
} from "./eval-blocks";
import { EvalCasePanel } from "./eval-case-panel";
import {
  EvalDataContext,
  EvalPanelContext,
  type EvalDataset,
} from "./eval-context";
import {
  Badge,
  BarList,
  Callout,
  Card,
  Columns,
  Comparison,
  DataTable,
  Details,
  Fact,
  Facts,
  Heatmap,
  Metric,
  MetricGrid,
  ReportChart,
  ReportDataContext,
  Side,
  Tab,
  Tabs,
  Timeline,
  TimelineEvent,
  type ReportDataset,
} from "./report-blocks";
import { type ParsedReport } from "./report-schema";

export type ReportFile = { id: string; name: string };

export type ReportSource = {
  files: readonly ReportFile[];
  queryKey: readonly unknown[];
  readText: (file: ReportFile) => Promise<string>;
  downloadUrl: (file: ReportFile) => Promise<string>;
};

const Heading = ({
  level,
  id,
  children,
}: {
  level: number;
  id: string;
  children: ReactNode;
}) =>
  createElement(
    `h${Math.min(Math.max(level, 1), 4)}`,
    {
      id,
      className:
        level <= 2
          ? "-mb-2 scroll-mt-6 pt-3 text-lg font-semibold tracking-tight"
          : "-mb-2 scroll-mt-6 text-base font-semibold",
    },
    children,
  );

const ReportSourceContext = createContext<{
  filesByName: ReadonlyMap<string, ReportFile>;
  source: ReportSource;
}>({
  filesByName: new Map(),
  source: {
    files: [],
    queryKey: [],
    readText: () => Promise.reject(new Error("No report source.")),
    downloadUrl: () => Promise.reject(new Error("No report source.")),
  },
});

const ReportLink = ({
  href,
  title,
  children,
}: {
  href: string;
  title?: string;
  children: ReactNode;
}) =>
  /^https:\/\//.test(href) ? (
    <a
      href={href}
      title={title}
      target="_blank"
      rel="noreferrer"
      className="underline underline-offset-4"
    >
      {children}
    </a>
  ) : href.startsWith("#") ? (
    <a href={href} className="underline underline-offset-4">
      {children}
    </a>
  ) : (
    <span>{children}</span>
  );

const ReportImage = ({ src, alt }: { src: string; alt?: string }) => {
  const { filesByName, source } = useContext(ReportSourceContext);
  const file = filesByName.get(src);
  const url = useQuery({
    queryKey: [...source.queryKey, "image", src, file?.id],
    queryFn: () => source.downloadUrl(file!),
    enabled: Boolean(file),
    staleTime: 240_000,
  });

  return file && url.data ? (
    <img
      src={url.data}
      alt={alt ?? ""}
      className="max-w-full rounded-xl border"
    />
  ) : null;
};

const ReportDocument = ({ children }: { children: ReactNode }) => (
  <>{children}</>
);

export type OpenCase = { eval?: string; case?: string };

export const TrainingReport = ({
  report,
  source,
  openCase,
  onOpenCase,
}: {
  report: ParsedReport;
  source: ReportSource;
  openCase?: OpenCase;
  onOpenCase?: (next: OpenCase) => void;
}) => {
  const filesByName = useMemo(
    () => new Map(source.files.map((file) => [file.name, file])),
    [source.files],
  );
  const results = useQueries({
    queries: report.dataFiles.map((name) => {
      const file = filesByName.get(name);

      return {
        queryKey: [...source.queryKey, "data", name, file?.id],
        queryFn: async () => {
          if (!file)
            throw new Error(`${name} is not attached to this version.`);

          return parseReportData(name, await source.readText(file));
        },
        staleTime: Infinity,
        retry: false,
      };
    }),
  });
  const evalResults = useQueries({
    queries: report.evalFiles.map((name) => {
      const file = filesByName.get(name);

      return {
        queryKey: [...source.queryKey, "eval", name, file?.id],
        queryFn: async () => {
          if (!file)
            throw new Error(`${name} is not attached to this version.`);

          return parseEval(await source.readText(file));
        },
        staleTime: Infinity,
        retry: false,
      };
    }),
  });
  const evals = new Map<string, EvalDataset>(
    report.evalFiles.map((name, index) => {
      const result = evalResults[index]!;

      return [
        name,
        result.isSuccess
          ? { status: "ready", index: result.data }
          : result.isError
            ? { status: "error", message: result.error.message }
            : { status: "loading" },
      ];
    }),
  );
  const [localCase, setLocalCase] = useState<OpenCase>({});
  const selected = openCase ?? localCase;
  const showCase = onOpenCase ?? setLocalCase;
  const [order, setOrder] = useState<readonly string[]>([]);
  const panelEval = selected.eval ? evals.get(selected.eval) : undefined;
  const panelIndex = panelEval?.status === "ready" ? panelEval.index : null;
  const datasets = new Map<string, ReportDataset>(
    report.dataFiles.map((name, index) => {
      const result = results[index]!;

      return [
        name,
        result.isSuccess
          ? { status: "ready", rows: result.data }
          : result.isError
            ? {
                status: "error",
                message: `Could not load ${name}: ${result.error.message}`,
              }
            : { status: "loading" },
      ];
    }),
  );

  return (
    <ReportSourceContext.Provider value={{ filesByName, source }}>
      <EvalDataContext.Provider value={evals}>
        <EvalPanelContext.Provider
          value={{
            open: (file, caseId, nextOrder) => {
              setOrder(nextOrder ?? []);
              showCase({ eval: file, case: caseId });
            },
          }}
        >
          <ReportDataContext.Provider value={datasets}>
            <article className="flex min-w-0 flex-col gap-5 text-sm leading-7 text-foreground/90 [&_blockquote]:border-l-2 [&_blockquote]:pl-4 [&_blockquote]:text-muted-foreground [&_code]:rounded [&_code]:bg-muted [&_code]:px-1 [&_code]:py-0.5 [&_code]:font-mono [&_code]:text-xs [&_hr]:border-border [&_ol]:list-decimal [&_ol]:pl-5 [&_p]:my-0 [&_pre]:overflow-x-auto [&_pre]:rounded-xl [&_pre]:bg-muted [&_pre]:p-4 [&_pre]:font-mono [&_pre]:text-xs [&_pre]:leading-6 [&_strong]:font-semibold [&_strong]:text-foreground [&_ul]:list-disc [&_ul]:pl-5">
              {Markdoc.renderers.react(report.content, React, {
                components: {
                  ReportDocument,
                  Heading,
                  ReportLink,
                  ReportImage,
                  MetricGrid,
                  Metric,
                  Callout,
                  Columns,
                  Card,
                  ReportChart,
                  DataTable,
                  Badge,
                  BarList,
                  Heatmap,
                  Comparison,
                  Side,
                  Facts,
                  Fact,
                  Timeline,
                  TimelineEvent,
                  Details,
                  Tabs,
                  Tab,
                  EvalSummary,
                  EvalBreakdown,
                  EvalHeadToHead,
                  EvalCaseGrid,
                  EvalExamples,
                  EvalCases,
                },
              })}
            </article>
            <EvalCasePanel
              index={panelIndex}
              caseId={selected.case ?? null}
              order={
                order.length
                  ? order
                  : (panelIndex?.cases.map((item) => item.id) ?? [])
              }
              onNavigate={(caseId) => showCase({ ...selected, case: caseId })}
              onClose={() => showCase({})}
            />
          </ReportDataContext.Provider>
        </EvalPanelContext.Provider>
      </EvalDataContext.Provider>
    </ReportSourceContext.Provider>
  );
};
