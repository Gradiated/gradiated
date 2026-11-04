import type { Meta, StoryObj } from "@storybook/react-vite";
import { useState } from "react";
import { userEvent, within } from "storybook/test";

import { ModelOption, modelOption } from "@/components/model-label";
import { State, States } from "@/stories/states";
import { OptionSelect, type Option } from "./option-select";

const regions = [
  { value: "us", label: "United States" },
  { value: "eu", label: "European Union" },
  { value: "ap", label: "Asia Pacific", disabled: true },
] as const satisfies readonly Option<string>[];

const models = [
  modelOption("z-ai/glm-5.3-flash"),
  modelOption("deepseek/deepseek-v4.1-flash"),
];

const meta = { title: "Components/Select" } satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

const RegionSelect = ({
  initial = "us",
  ...props
}: {
  initial?: string;
  disabled?: boolean;
  placeholder?: string;
}) => {
  const [value, setValue] = useState(initial);

  return (
    <OptionSelect
      label="Region"
      className="w-56"
      value={value}
      options={regions}
      onValueChange={setValue}
      {...props}
    />
  );
};

export const States_: Story = {
  name: "States",
  render: () => (
    <States>
      <State label="Selected">
        <RegionSelect />
      </State>
      <State label="Placeholder">
        <RegionSelect initial="" placeholder="Choose a region" />
      </State>
      <State label="Disabled">
        <RegionSelect disabled />
      </State>
    </States>
  ),
};

export const Open: Story = {
  render: () => (
    <States>
      <RegionSelect />
    </States>
  ),
  play: async ({ canvasElement }) => {
    await userEvent.click(
      within(canvasElement).getByRole("combobox", { name: "Region" }),
    );
    await within(document.body).findByRole("option", { name: "Asia Pacific" });
  },
};

const ModelSelect = () => {
  const [value, setValue] = useState<string>("z-ai/glm-5.3-flash");

  return (
    <OptionSelect
      label="Model"
      className="w-64"
      value={value}
      options={models}
      onValueChange={setValue}
      renderOption={ModelOption}
    />
  );
};

export const WithIcons: Story = {
  render: () => (
    <States>
      <ModelSelect />
    </States>
  ),
  play: async ({ canvasElement }) => {
    await userEvent.click(
      within(canvasElement).getByRole("combobox", { name: "Model" }),
    );
    await within(document.body).findByRole("option", {
      name: "DeepSeek V4.1 Flash",
    });
  },
};
