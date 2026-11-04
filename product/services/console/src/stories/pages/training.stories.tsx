import type { Meta } from "@storybook/react-vite";
import { http, HttpResponse } from "msw";

import type { components } from "@/api/schema";
import { handlers, handlersFor, staffUser, version } from "@/stories/handlers";
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
  { versions = [version] }: { versions?: TaskVersion[] } = {},
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
    http.get(filesPath, () =>
      HttpResponse.json({
        data: entries.map(({ content: _content, ...file }) => file),
      }),
    ),
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
    http.get(`${filesPath}/:fileId/download`, () =>
      HttpResponse.json({
        url: "https://example.invalid/download",
        expires_at: version.created_at,
      }),
    ),
  ];
};

export const Tasks: PageStory = { args: { path: "/tasks" } };
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
