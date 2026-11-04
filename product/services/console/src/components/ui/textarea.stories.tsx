import type { Meta, StoryObj } from "@storybook/react-vite";

import { State, States } from "@/stories/states";
import { Textarea } from "./textarea";

const meta = { title: "Components/Textarea" } satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

const prompt =
  "You are a support assistant. Answer briefly and cite the relevant help article.";

export const States_: Story = {
  name: "States",
  render: () => (
    <States className="grid-cols-[repeat(auto-fill,minmax(18rem,1fr))]">
      <State label="Empty">
        <Textarea aria-label="Empty" placeholder="Write a system prompt…" />
      </State>
      <State label="Filled">
        <Textarea aria-label="Filled" defaultValue={prompt} />
      </State>
      <State label="Invalid">
        <Textarea aria-label="Invalid" aria-invalid defaultValue={prompt} />
      </State>
      <State label="Disabled">
        <Textarea aria-label="Disabled" disabled defaultValue={prompt} />
      </State>
      <State label="Long content">
        <Textarea
          aria-label="Long content"
          rows={4}
          defaultValue={Array.from({ length: 8 }, () => prompt).join("\n")}
        />
      </State>
    </States>
  ),
};
