import type { Meta, StoryObj } from "@storybook/react-vite";
import { LoaderCircle, Plus, Trash2, Upload } from "lucide-react";

import { State, States } from "@/stories/states";
import { Button } from "./button";

const VARIANTS = [
  "default",
  "secondary",
  "outline",
  "ghost",
  "link",
  "destructive",
] as const;
const SIZES = ["xs", "sm", "default", "lg"] as const;
const ICON_SIZES = ["icon-xs", "icon-sm", "icon", "icon-lg"] as const;

const meta = { title: "Components/Button" } satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

export const Variants: Story = {
  render: () => (
    <States>
      {VARIANTS.map((variant) => (
        <State key={variant} label={variant}>
          <Button variant={variant}>Save changes</Button>
        </State>
      ))}
    </States>
  ),
};

export const Sizes: Story = {
  render: () => (
    <States>
      {SIZES.map((size) => (
        <State key={size} label={size}>
          <Button size={size}>Save changes</Button>
        </State>
      ))}
      {ICON_SIZES.map((size) => (
        <State key={size} label={size}>
          <Button size={size} variant="outline" aria-label="Add">
            <Plus />
          </Button>
        </State>
      ))}
    </States>
  ),
};

export const WithIcon: Story = {
  render: () => (
    <States>
      <State label="Leading icon">
        <Button>
          <Upload />
          Upload
        </Button>
      </State>
      <State label="Outline with icon">
        <Button variant="outline">
          <Plus />
          Add model
        </Button>
      </State>
      <State label="Destructive with icon">
        <Button variant="destructive">
          <Trash2 />
          Delete
        </Button>
      </State>
    </States>
  ),
};

export const Disabled: Story = {
  render: () => (
    <States>
      {VARIANTS.map((variant) => (
        <State key={variant} label={variant}>
          <Button variant={variant} disabled>
            Save changes
          </Button>
        </State>
      ))}
    </States>
  ),
};

export const Loading: Story = {
  render: () => (
    <States>
      <State label="Primary">
        <Button disabled>
          <LoaderCircle className="animate-spin" />
          Saving…
        </Button>
      </State>
      <State label="Outline">
        <Button variant="outline" disabled>
          <LoaderCircle className="animate-spin" />
          Loading
        </Button>
      </State>
    </States>
  ),
};
