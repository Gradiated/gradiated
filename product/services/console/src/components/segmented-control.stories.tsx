import type { Meta, StoryObj } from "@storybook/react-vite";
import { useState } from "react";

import { State, States } from "@/stories/states";
import type { Option } from "./option-select";
import { SegmentedControl } from "./segmented-control";

const meta = { title: "Components/Segmented control" } satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

const Control = ({
  options,
  initial,
}: {
  options: Option<string>[];
  initial: string;
}) => {
  const [value, setValue] = useState(initial);

  return (
    <SegmentedControl
      label="Range"
      value={value}
      options={options}
      onValueChange={setValue}
    />
  );
};

export const States_: Story = {
  name: "States",
  render: () => (
    <States>
      <State label="Two options">
        <Control
          initial="monthly"
          options={[
            { value: "monthly", label: "Monthly" },
            { value: "yearly", label: "Yearly" },
          ]}
        />
      </State>
      <State label="Four options">
        <Control
          initial="7d"
          options={[
            { value: "24h", label: "24h" },
            { value: "7d", label: "7d" },
            { value: "30d", label: "30d" },
            { value: "90d", label: "90d" },
          ]}
        />
      </State>
      <State label="Disabled option">
        <Control
          initial="python"
          options={[
            { value: "python", label: "Python" },
            { value: "typescript", label: "TypeScript" },
            { value: "go", label: "Go", disabled: true },
          ]}
        />
      </State>
    </States>
  ),
};
