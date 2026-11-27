import type { Meta, StoryObj } from "@storybook/react-vite";

import { EVAL_STATUS, RUN_STATUS } from "@/lib/grad/labels";
import type { EvalStatus, RunStatus } from "@/lib/grad/types";
import { State, States } from "@/stories/states";
import { EvalStatusBadge, RunStatusBadge } from "./status-badge";

const meta = {
  title: "Components/Training/Status badge",
  parameters: { layout: "fullscreen" },
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

export const RunStatuses: Story = {
  render: () => (
    <States>
      {(Object.keys(RUN_STATUS) as RunStatus[]).map((status) => (
        <State key={status} label={status}>
          <RunStatusBadge status={status} />
        </State>
      ))}
    </States>
  ),
};

export const EvalStatuses: Story = {
  render: () => (
    <States>
      {(Object.keys(EVAL_STATUS) as EvalStatus[]).map((status) => (
        <State key={status} label={status}>
          <EvalStatusBadge status={status} />
        </State>
      ))}
    </States>
  ),
};
