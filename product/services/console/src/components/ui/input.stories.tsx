import type { Meta, StoryObj } from "@storybook/react-vite";

import { State, States } from "@/stories/states";
import { Input } from "./input";

const meta = { title: "Components/Input" } satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

export const States_: Story = {
  name: "States",
  render: () => (
    <States>
      <State label="Empty">
        <Input aria-label="Empty" placeholder="support-triage" />
      </State>
      <State label="Filled">
        <Input aria-label="Filled" defaultValue="support-triage" />
      </State>
      <State label="Focused">
        <Input aria-label="Focused" defaultValue="support-triage" autoFocus />
      </State>
      <State label="Invalid">
        <Input
          aria-label="Invalid"
          aria-invalid
          defaultValue="Support Triage!"
        />
      </State>
      <State label="Disabled">
        <Input aria-label="Disabled" disabled defaultValue="support-triage" />
      </State>
      <State label="Read only">
        <Input
          aria-label="Read only"
          readOnly
          defaultValue="gr_live_••••3f9a"
        />
      </State>
      <State label="Password">
        <Input aria-label="Password" type="password" defaultValue="secret" />
      </State>
      <State label="File">
        <Input aria-label="File" type="file" />
      </State>
    </States>
  ),
};
