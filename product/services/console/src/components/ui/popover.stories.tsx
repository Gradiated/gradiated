import type { Meta, StoryObj } from "@storybook/react-vite";
import { userEvent, within } from "storybook/test";

import { Canvas } from "@/stories/states";
import { Button } from "./button";
import { Field, FieldLabel } from "./field";
import { Input } from "./input";
import { Popover, PopoverContent, PopoverTrigger } from "./popover";

const meta = { title: "Components/Popover" } satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

const story = (align: "start" | "center" | "end"): Story => ({
  render: () => (
    <Canvas className="flex justify-center pt-16">
      <Popover>
        <PopoverTrigger asChild>
          <Button variant="outline">Edit limit</Button>
        </PopoverTrigger>
        <PopoverContent align={align} className="w-64">
          <Field>
            <FieldLabel htmlFor={`popover-${align}`}>Monthly limit</FieldLabel>
            <Input id={`popover-${align}`} defaultValue="500" />
          </Field>
        </PopoverContent>
      </Popover>
    </Canvas>
  ),
  play: async ({ canvasElement }) => {
    await userEvent.click(
      within(canvasElement).getByRole("button", { name: "Edit limit" }),
    );
    await within(document.body).findByLabelText("Monthly limit");
  },
});

export const AlignStart = story("start");
export const AlignCenter = story("center");
export const AlignEnd = story("end");
