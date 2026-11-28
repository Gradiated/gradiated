import type { Meta, StoryObj } from "@storybook/react-vite";

import {
  completedRun,
  failedRun,
  queuedRun,
  runEvents,
  runningRun,
  stoppedRun,
} from "@/stories/grad-fixtures";
import { Canvas } from "@/stories/states";
import { EvalChart, LossChart } from "./run-charts";
import { RunProgress } from "./run-progress";
import { RunTimeline } from "./run-timeline";

const meta = {
  title: "Components/Training/Run progress",
  parameters: { layout: "fullscreen" },
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

export const Phases: Story = {
  render: () => (
    <Canvas className="space-y-5">
      {[queuedRun, runningRun, completedRun, stoppedRun, failedRun].map(
        (run) => (
          <RunProgress key={run.id} run={run} />
        ),
      )}
    </Canvas>
  ),
};

export const Charts: Story = {
  render: () => (
    <Canvas className="grid gap-5 lg:grid-cols-2">
      <LossChart events={runEvents[runningRun.id] ?? []} />
      <EvalChart events={runEvents[runningRun.id] ?? []} />
      <LossChart events={[]} />
      <EvalChart events={[]} />
    </Canvas>
  ),
};

export const Timeline: Story = {
  render: () => (
    <Canvas className="grid max-w-3xl gap-5">
      <RunTimeline events={runEvents[runningRun.id] ?? []} live={null} />
      <RunTimeline events={runEvents[completedRun.id] ?? []} live={null} />
    </Canvas>
  ),
};
