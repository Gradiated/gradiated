import type { Meta, StoryObj } from "@storybook/react-vite";

import { State, States } from "@/stories/states";
import { Avatar, AvatarFallback, AvatarImage } from "./avatar";

const image =
  "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 40 40'><rect width='40' height='40' fill='%236e7f31'/><circle cx='20' cy='16' r='7' fill='%23f6f5f1'/><rect x='8' y='26' width='24' height='14' rx='7' fill='%23f6f5f1'/></svg>";

const meta = { title: "Components/Avatar" } satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

export const States_: Story = {
  name: "States",
  render: () => (
    <States>
      <State label="Image">
        <Avatar>
          <AvatarImage src={image} alt="Alex Example" />
          <AvatarFallback>AE</AvatarFallback>
        </Avatar>
      </State>
      <State label="Initials fallback">
        <Avatar>
          <AvatarFallback>AE</AvatarFallback>
        </Avatar>
      </State>
      <State label="Broken image">
        <Avatar>
          <AvatarImage src="data:image/png;base64,broken" alt="Sam Lee" />
          <AvatarFallback>SL</AvatarFallback>
        </Avatar>
      </State>
      <State label="Small">
        <Avatar className="size-6 text-[10px]">
          <AvatarFallback>AE</AvatarFallback>
        </Avatar>
      </State>
      <State label="Large">
        <Avatar className="size-12">
          <AvatarFallback>AE</AvatarFallback>
        </Avatar>
      </State>
    </States>
  ),
};
