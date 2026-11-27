import type { Meta, StoryObj } from "@storybook/react-vite";

import { completedRun, evals, plan, records } from "@/stories/grad-fixtures";
import { Canvas } from "@/stories/states";
import { EvalReportCard } from "./eval-report-card";
import { EvalSummaryTable } from "./eval-summary-table";
import { PlanSummary } from "./plan-summary";
import { RecordsTable } from "./records-preview";

const meta = {
  title: "Components/Training/Reports",
  parameters: { layout: "fullscreen" },
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

const base = {
  selectedStep: 1200,
  bestStep: 1200,
  finalStep: 1500,
  trainRecords: 11_856,
  evalRecords: 624,
  warnings: [],
};

export const EvalReports: Story = {
  render: () => (
    <Canvas className="grid max-w-5xl gap-5 lg:grid-cols-2">
      <EvalReportCard
        kind="dpo"
        report={completedRun.evalReport}
        checkpointEvals={completedRun.checkpointEvals}
      />
      <EvalReportCard
        kind="sft"
        report={{
          ...base,
          metricName: "eval_loss",
          metricMode: "min",
          evalLoss: 0.6121,
          evalTokenAccuracy: 0.743,
          trainedTokenFraction: 0.41,
          trainExamples: 11_856,
          evalExamples: 624,
          truncated: 3,
        }}
        checkpointEvals={[]}
      />
      <EvalReportCard
        kind="router"
        report={{
          ...base,
          metricName: "eval_loss",
          evalLoss: 0.3012,
          candidates: ["qwen3-8b", "gpt-4.1-mini"],
          fallbackModel: "gpt-4.1-mini",
          fallbackQuality: 0.83,
          routesAnyTraffic: true,
          paretoSummary: {
            targetMaxDrop: 0.02,
            routedQuality: 0.818,
            qualityDrop: 0.012,
            qualityDropCi95: [0.004, 0.021],
            offloadRate: 0.64,
            costSavingsPct: 0.52,
            ece: 0.031,
            threshold: 0.71,
            temperature: 1,
          },
        }}
        checkpointEvals={[]}
      />
      <EvalReportCard
        kind="embedding"
        report={{
          ...base,
          metricName: "recall_at_10",
          metricMode: "max",
          recallAt1: 0.61,
          recallAt5: 0.84,
          recallAt10: 0.91,
          mrr: 0.712,
          corpusSize: 8_400,
          baseline: {
            recallAt1: 0.44,
            recallAt5: 0.7,
            recallAt10: 0.79,
            mrr: 0.55,
          },
        }}
        checkpointEvals={[]}
      />
      <EvalReportCard kind="cartridge" report={null} checkpointEvals={[]} />
    </Canvas>
  ),
};

export const EvalSummary: Story = {
  render: () => (
    <Canvas>
      <EvalSummaryTable
        summaries={evals[0]?.summary ?? []}
        baseline={evals[0]?.baseline ?? null}
      />
    </Canvas>
  ),
};

export const RunPlan: Story = {
  render: () => (
    <Canvas className="max-w-4xl">
      <PlanSummary plan={plan} />
    </Canvas>
  ),
};

export const DatasetRecords: Story = {
  render: () => (
    <Canvas>
      <div className="overflow-hidden rounded-lg border bg-card">
        <RecordsTable records={records} loading={false} />
      </div>
    </Canvas>
  ),
};
