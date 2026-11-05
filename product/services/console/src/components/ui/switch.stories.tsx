import type { Meta, StoryObj } from "@storybook/react-vite";
import { useState } from "react";

import { State, States } from "@/stories/states";
import { Label } from "./label";
import { Switch } from "./switch";

const meta = { title: "Components/Switch" } satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

const Row = ({
  label,
  initial = false,
  disabled,
}: {
  label: string;
  initial?: boolean;
  disabled?: boolean;
}) => {
  const [checked, setChecked] = useState(initial);

  return (
    <State label={label}>
      <Label className="flex items-center gap-2 font-normal">
        <Switch
          checked={checked}
          onCheckedChange={setChecked}
          disabled={disabled ?? false}
        />
        Auto top-up
      </Label>
    </State>
  );
};

export const States_: Story = {
  name: "States",
  render: () => (
    <States>
      <Row label="Off" />
      <Row label="On" initial />
      <Row label="Disabled off" disabled />
      <Row label="Disabled on" disabled initial />
    </States>
  ),
};
