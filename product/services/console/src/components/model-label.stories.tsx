import type { Meta, StoryObj } from "@storybook/react-vite";

import { State, States } from "@/stories/states";
import { ModelLabel } from "./model-label";

const meta = { title: "Components/Model label" } satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

export const States_: Story = {
  name: "States",
  render: () => (
    <States>
      <State label="Hosted model">
        <ModelLabel id="z-ai/glm-5.3-flash" />
      </State>
      <State label="Another provider">
        <ModelLabel id="deepseek/deepseek-v4.1-flash" />
      </State>
      <State label="Unknown provider">
        <ModelLabel id="acme/custom-model" />
      </State>
      <State label="Custom label">
        <ModelLabel id="z-ai/glm-5.3-flash" label="support-assistant" />
      </State>
      <State label="No model">
        <ModelLabel id={null} label="Not set" />
      </State>
      <State label="Truncated">
        <ModelLabel
          id="z-ai/glm-5.3-flash"
          label="a-very-long-fine-tuned-model-name-v12"
          className="w-40"
        />
      </State>
    </States>
  ),
};
