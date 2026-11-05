import type { Meta, StoryObj } from "@storybook/react-vite";
import { Info } from "lucide-react";

import { Canvas } from "@/stories/states";
import { Button } from "./button";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "./tooltip";

const meta = { title: "Components/Tooltip" } satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

const SIDES = ["top", "right", "bottom", "left"] as const;

export const Sides: Story = {
  render: () => (
    <TooltipProvider>
      <Canvas className="grid grid-cols-2 place-items-center gap-24 p-24">
        {SIDES.map((side) => (
          <Tooltip key={side} open>
            <TooltipTrigger asChild>
              <Button variant="outline">{side}</Button>
            </TooltipTrigger>
            <TooltipContent side={side}>Tooltip on the {side}</TooltipContent>
          </Tooltip>
        ))}
      </Canvas>
    </TooltipProvider>
  ),
};

export const IconTrigger: Story = {
  render: () => (
    <TooltipProvider>
      <Canvas className="flex items-center gap-2 p-24 text-sm">
        Cached input tokens
        <Tooltip open>
          <TooltipTrigger aria-label="About cached input tokens">
            <Info className="size-4 text-muted-foreground" />
          </TooltipTrigger>
          <TooltipContent className="max-w-56">
            Tokens served from the prompt cache are billed at a lower rate.
          </TooltipContent>
        </Tooltip>
      </Canvas>
    </TooltipProvider>
  ),
};
