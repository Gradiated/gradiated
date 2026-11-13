import type { Meta } from "@storybook/react-vite";
import { delay, http, HttpResponse } from "msw";

import type { components } from "@/api/schema";
import {
  noTasksHandlers,
  handlers,
  handlersFor,
  staffUser,
  version,
} from "@/stories/handlers";
import { Page, pageMeta, type PageStory } from "@/stories/page-story";
import { sampleReport, sampleReportData } from "@/stories/report-fixture";

const meta = { ...pageMeta, title: "Pages/Training" } satisfies Meta<
  typeof Page
>;

export default meta;

const versionPath = `/tasks/support-assistant/versions/${version.id}`;
const filesPath =
  "/api/v1/workspaces/:workspaceId/tasks/:task/versions/:versionId/files";
const reportFiles = { "report.md": sampleReport, ...sampleReportData };

type TaskVersion = components["schemas"]["TaskVersion"];

const versionFiles = (
  files: Record<string, string>,
  {
    versions = [version],
    listDelayMs = 0,
  }: { versions?: TaskVersion[]; listDelayMs?: number } = {},
) => {
  const entries = Object.entries(files).map(([name, content], index) => ({
    id: `00000000-0000-4000-8000-${String(index + 1).padStart(12, "0")}`,
    name,
    content_type: name.endsWith(".md") ? "text/markdown" : "text/csv",
    size_bytes: new TextEncoder().encode(content).length,
    created_at: version.created_at,
    content,
  }));
  const find = (id: unknown) => entries.find((entry) => entry.id === id);

  return [
    http.get("/api/v1/workspaces/:workspaceId/tasks/:task/versions", () =>
      HttpResponse.json({ data: versions, next_cursor: null }),
    ),
    http.get(filesPath, async () => {
      if (listDelayMs) await delay(listDelayMs);

      return HttpResponse.json({
        data: entries.map(({ content: _content, ...file }) => file),
      });
    }),
    http.get(`${filesPath}/:fileId/content`, ({ params }) => {
      const file = find(params.fileId);
      return file
        ? HttpResponse.json({
            name: file.name,
            content_type: file.content_type,
            content: file.content,
          })
        : HttpResponse.json({ detail: "Not found" }, { status: 404 });
    }),
    http.post(filesPath, () => {
      return HttpResponse.json({
        id: "benchmark-upload",
        upload_url: `${location.origin}/storybook-benchmark-upload`,
        expires_at: version.created_at,
      });
    }),
    http.put("/storybook-benchmark-upload", async ({ request }) => {
      const content = await request.text();
      const index = entries.findIndex((file) => file.name === "benchmark.json");
      const next = {
        id: "benchmark-upload",
        name: "benchmark.json",
        content_type: "application/json",
        size_bytes: content.length,
        created_at: version.created_at,
        content,
      };
      if (index < 0) entries.push(next);
      else entries[index] = next;
      return new HttpResponse(null, { status: 200 });
    }),
    http.put(`${filesPath}/:fileId`, () =>
      HttpResponse.json(entries.find((file) => file.id === "benchmark-upload")),
    ),
    http.get(`${filesPath}/:fileId/download`, () =>
      HttpResponse.json({
        url: "https://example.invalid/download",
        expires_at: version.created_at,
      }),
    ),
    ...shareHandlers(),
  ];
};

const shareSignature = "a".repeat(43);

const shareHandlers = () => [
  http.get(
    "/api/v1/workspaces/:workspaceId/tasks/:task/versions/:versionId/share",
    ({ params }) =>
      HttpResponse.json({
        version_id: params.versionId,
        signature: shareSignature,
      }),
  ),
];

const sharedReportFiles = (files: Record<string, string>) => {
  const entries = Object.entries(files).map(([name, content], index) => ({
    id: `00000000-0000-4000-8000-${String(index + 1).padStart(12, "0")}`,
    name,
    content_type: name.endsWith(".md") ? "text/markdown" : "text/csv",
    size_bytes: new TextEncoder().encode(content).length,
    created_at: version.created_at,
    content,
  }));
  const base = "/api/v1/shared-reports/:versionId/:signature";

  return [
    http.get(base, ({ params }) =>
      params.signature === shareSignature
        ? HttpResponse.json({
            task: "support-assistant",
            version: version.name,
            base_model_id: version.base_model_id,
            created_at: version.created_at,
            adapter: {
              rank: version.adapter.rank,
              size_bytes: version.adapter.size_bytes,
              checkpoint: null,
            },
            files: entries.map(({ content: _content, ...file }) => file),
          })
        : HttpResponse.json(
            { detail: "The report was not found." },
            { status: 404 },
          ),
    ),
    http.get(`${base}/files/:fileId/content`, ({ params }) => {
      const file = entries.find((entry) => entry.id === params.fileId);
      return file
        ? HttpResponse.json({
            name: file.name,
            content_type: file.content_type,
            content: file.content,
          })
        : HttpResponse.json({ detail: "Not found" }, { status: 404 });
    }),
  ];
};

export const Tasks: PageStory = { args: { path: "/tasks" } };
export const NoTasks: PageStory = {
  args: { path: "/tasks" },
  parameters: { msw: noTasksHandlers() },
};
export const NoTasksProjectStarted: PageStory = {
  args: { path: "/tasks" },
  parameters: { msw: noTasksHandlers(true) },
};
export const Task: PageStory = {
  args: { path: "/tasks/support-assistant" },
};
export const TestResults: PageStory = {
  args: { path: "/tasks/support-assistant" },
  parameters: { taskDetail: "results" },
};
export const VersionReport: PageStory = {
  args: { path: versionPath },
  parameters: { msw: [...versionFiles(reportFiles), ...handlers] },
};
export const SharedReport: PageStory = {
  args: { path: `/share/${version.id}/${shareSignature}` },
  parameters: { msw: [...sharedReportFiles(reportFiles), ...handlers] },
};
export const SharedReportRevoked: PageStory = {
  args: { path: `/share/${version.id}/${"b".repeat(43)}` },
  parameters: { msw: [...sharedReportFiles(reportFiles), ...handlers] },
};
export const VersionReadyToPromote: PageStory = {
  args: { path: versionPath },
  parameters: {
    msw: [
      ...versionFiles(reportFiles, {
        versions: [{ ...version, is_production: false }],
      }),
      ...handlers,
    ],
  },
};
export const VersionWithoutReport: PageStory = {
  args: { path: versionPath },
  parameters: { msw: [...versionFiles({}), ...handlers] },
};
export const VersionAsStaff: PageStory = {
  args: { path: versionPath },
  parameters: {
    msw: [
      ...versionFiles({
        ...reportFiles,
        "report.md": `${sampleReport}\n{% callout type="tip" %}Unknown callout type.{% /callout %}\n`,
      }),
      ...handlersFor(staffUser),
    ],
  },
};
export const VersionMobile: PageStory = {
  ...VersionReport,
  tags: ["mobile"],
};

const manualBenchmark = JSON.stringify({
  schema_version: 1,
  comparison_model_id: "anthropic/claude-sonnet-5-5",
  workload: "Support tool selection",
  notes: "64 task checks; separate 96-request latency benchmark.",
  cost: {
    unit: "task",
    fine_tuned: 266433,
    comparison: null,
    basis: "estimated",
  },
  speed: {
    unit: "latency_seconds",
    fine_tuned: 2.58,
    comparison: null,
    statistic: "median",
  },
  quality: {
    metric: "Task success",
    fine_tuned: 76.5625,
    comparison: null,
    sample_size: 64,
  },
});
const comparedBenchmark = JSON.stringify({
  schema_version: 1,
  comparison_model_id: "anthropic/claude-sonnet-5-5",
  workload: "Full agent runs",
  notes: "",
  cost: {
    unit: "task",
    fine_tuned: 3_320_000,
    comparison: 60_000_000,
    basis: "measured",
  },
  speed: {
    unit: "latency_seconds",
    fine_tuned: 11.8,
    comparison: 14.6,
    statistic: "mean",
  },
  quality: {
    metric: "Runs passed",
    fine_tuned: 100,
    comparison: 75,
    sample_size: 72,
    outcome: { better: 18, same: 54, worse: 0 },
  },
});
export const ComparedBenchmarks: PageStory = {
  args: { path: versionPath },
  parameters: {
    msw: [
      ...versionFiles({ ...reportFiles, "benchmark.json": comparedBenchmark }),
      ...handlersFor(staffUser),
    ],
  },
};
export const ManualBenchmarks: PageStory = {
  args: { path: versionPath },
  parameters: {
    msw: [
      ...versionFiles({ ...reportFiles, "benchmark.json": manualBenchmark }),
      ...handlersFor(staffUser),
    ],
  },
};
export const ManualBenchmarksSlowList: PageStory = {
  args: { path: versionPath },
  parameters: {
    msw: [
      ...versionFiles(
        { "benchmark.json": manualBenchmark },
        { listDelayMs: 1500 },
      ),
      ...handlersFor(staffUser),
    ],
  },
};
export const ManualBenchmarksListRetry: PageStory = {
  args: { path: versionPath },
  parameters: {
    msw: [
      http.get(
        filesPath,
        () =>
          HttpResponse.json(
            { detail: "Temporary listing failure" },
            { status: 503 },
          ),
        { once: true },
      ),
      ...versionFiles({ "benchmark.json": manualBenchmark }),
      ...handlersFor(staffUser),
    ],
  },
};
export const ManualBenchmarksTable: PageStory = {
  args: { path: "/tasks" },
  parameters: {
    msw: [
      http.get("/api/v1/workspaces/:workspaceId/tasks", () =>
        HttpResponse.json({
          data: [
            {
              id: "00000000-0000-4000-8000-000000000003",
              name: version.task,
              comparison_model_id: "anthropic/claude-sonnet-5-5",
              base_model_id: version.base_model_id,
              latest_version: version,
              latest_run: null,
              workload_benchmark: JSON.parse(comparedBenchmark),
            },
          ],
        }),
      ),
      ...handlers,
    ],
  },
};
