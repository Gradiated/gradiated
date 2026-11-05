import type { Meta, StoryObj } from "@storybook/react-vite";
import type { ComponentProps } from "react";

import { State, States } from "@/stories/states";
import { Checkbox } from "./checkbox";
import { Label } from "./label";

const meta = { title: "Components/Checkbox" } satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

const Row = ({
  label,
  ...props
}: ComponentProps<typeof Checkbox> & { label: string }) => (
  <State label={label}>
    <Label className="flex items-center gap-2 font-normal">
      <Checkbox {...props} />
      Email me about failed top-ups
    </Label>
  </State>
);

export const States_: Story = {
  name: "States",
  render: () => (
    <States>
      <Row label="Unchecked" />
      <Row label="Checked" defaultChecked />
      <Row label="Indeterminate" checked="indeterminate" />
      <Row label="Invalid" aria-invalid />
      <Row label="Disabled" disabled />
      <Row label="Disabled checked" disabled defaultChecked />
    </States>
  ),
};
