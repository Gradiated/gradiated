import type { Meta, StoryObj } from "@storybook/react-vite";
import { useState } from "react";
import { expect, userEvent, within } from "storybook/test";

import { ModelOption, modelOption } from "@/components/model-label";
import { State, States } from "@/stories/states";
import { OptionCombobox } from "./option-combobox";
import type { Option } from "./option-select";

const models: Option<string>[] = [
  { ...modelOption("z-ai/glm-5.3-flash"), group: "Hosted models" },
  { ...modelOption("deepseek/deepseek-v4.1-flash"), group: "Hosted models" },
  {
    value: "support-assistant",
    label: "support-assistant",
    group: "Your models",
  },
  {
    value: "triage-v2",
    label: "triage-v2",
    group: "Your models",
    disabled: true,
  },
];

const many: Option<string>[] = Array.from({ length: 40 }, (_, index) => ({
  value: `model-${index + 1}`,
  label: `Model ${index + 1}`,
}));

const meta = { title: "Components/Combobox" } satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

const Combobox = ({
  options = models,
  initial = "z-ai/glm-5.3-flash",
  disabled = false,
  placeholder,
}: {
  options?: Option<string>[];
  initial?: string;
  disabled?: boolean;
  placeholder?: string;
}) => {
  const [value, setValue] = useState(initial);

  return (
    <OptionCombobox
      label="Model"
      className="w-64"
      value={value}
      options={options}
      onValueChange={setValue}
      disabled={disabled}
      {...(placeholder ? { placeholder } : {})}
      renderOption={ModelOption}
    />
  );
};

const open = async (canvasElement: HTMLElement) => {
  await userEvent.click(
    within(canvasElement).getByRole("combobox", { name: "Model" }),
  );
  return within(document.body);
};

export const States_: Story = {
  name: "States",
  render: () => (
    <States>
      <State label="Selected">
        <Combobox />
      </State>
      <State label="Placeholder">
        <Combobox initial="" placeholder="Choose a model" />
      </State>
      <State label="Disabled">
        <Combobox disabled />
      </State>
    </States>
  ),
};

export const Open: Story = {
  render: () => (
    <States>
      <Combobox />
    </States>
  ),
  play: async ({ canvasElement }) => {
    const body = await open(canvasElement);
    await body.findByRole("group", { name: "Your models" });
  },
};

export const Searching: Story = {
  render: () => (
    <States>
      <Combobox />
    </States>
  ),
  play: async ({ canvasElement }) => {
    const body = await open(canvasElement);
    await userEvent.type(
      await body.findByRole("combobox", { name: "Search model" }),
      "deepseek",
    );
    await expect(
      await body.findByRole("option", { name: "DeepSeek V4.1 Flash" }),
    ).toBeVisible();
  },
};

export const NoResults: Story = {
  render: () => (
    <States>
      <Combobox />
    </States>
  ),
  play: async ({ canvasElement }) => {
    const body = await open(canvasElement);
    await userEvent.type(
      await body.findByRole("combobox", { name: "Search model" }),
      "qqqq",
    );
    await body.findByText("No models found.");
  },
};

export const LongList: Story = {
  render: () => (
    <States>
      <Combobox options={many} initial="model-1" />
    </States>
  ),
  play: async ({ canvasElement }) => {
    const body = await open(canvasElement);
    await body.findByRole("option", { name: "Model 40" });
  },
};
