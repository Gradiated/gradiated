import type { Meta, StoryObj } from "@storybook/react-vite";
import { CircleCheck } from "lucide-react";

import { State, States } from "@/stories/states";
import { Badge } from "./badge";

const VARIANTS = [
  "default",
  "secondary",
  "outline",
  "destructive",
  "ghost",
  "link",
] as const;

const meta = { title: "Components/Badge" } satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

export const Variants: Story = {
  render: () => (
    <States>
      {VARIANTS.map((variant) => (
        <State key={variant} label={variant}>
          <Badge variant={variant}>Production</Badge>
        </State>
      ))}
      <State label="With icon">
        <Badge variant="secondary">
          <CircleCheck />
          Ready
        </Badge>
      </State>
    </States>
  ),
};
