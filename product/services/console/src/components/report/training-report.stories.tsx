import type { Meta, StoryObj } from "@storybook/react-vite";
import { QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";

import { evalReport, evalReportData } from "@/stories/eval-fixture";
import { createStoryQueryClient } from "@/stories/query-client";
import {
  everyBlockReport,
  everyBlockReportData,
  sampleReport,
  sampleReportData,
} from "@/stories/report-fixture";
import { parseReport } from "./report-schema";
import { TrainingReport, type ReportSource } from "./training-report";

const source = (files: Record<string, string>): ReportSource => {
  const entries = Object.keys(files).map((name) => ({ id: name, name }));

  return {
    files: entries,
    queryKey: ["story-report", Object.keys(files).join(",")],
    readText: async (file) => files[file.name] ?? "",
    downloadUrl: async () => "https://example.invalid/download",
  };
};

const Report = ({
  markdown,
  files,
}: {
  markdown: string;
  files: Record<string, string>;
}) => {
  const [client] = useState(() => createStoryQueryClient());

  return (
    <QueryClientProvider client={client}>
      <div className="min-h-screen bg-background p-8">
        <div className="mx-auto max-w-3xl">
          <TrainingReport
            report={parseReport(markdown)}
            source={source(files)}
          />
        </div>
      </div>
    </QueryClientProvider>
  );
};

const meta = {
  title: "Pages/Training/Blocks/Training report",
  parameters: { layout: "fullscreen" },
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

export const EveryBlock: Story = {
  render: () => (
    <Report markdown={everyBlockReport} files={everyBlockReportData} />
  ),
};

export const Full: Story = {
  render: () => <Report markdown={sampleReport} files={sampleReportData} />,
};

export const Eval: Story = {
  render: () => <Report markdown={evalReport} files={evalReportData} />,
};

export const MissingData: Story = {
  render: () => <Report markdown={sampleReport} files={{}} />,
};

export const TextOnly: Story = {
  render: () => (
    <Report
      files={{}}
      markdown={`## Summary

This version was trained on **4,812** tickets. See [the PEFT docs](https://huggingface.co/docs/peft) for loading it.

> Shipping questions are slightly worse than before.

\`\`\`bash
vllm serve Qwen/Qwen3-8B --enable-lora
\`\`\`
`}
    />
  ),
};
