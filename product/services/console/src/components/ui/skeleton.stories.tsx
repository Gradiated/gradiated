import type { Meta, StoryObj } from "@storybook/react-vite";

import { State, States } from "@/stories/states";
import { Skeleton } from "./skeleton";

const meta = { title: "Components/Skeleton" } satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

export const Shapes: Story = {
  render: () => (
    <States>
      <State label="Text">
        <div className="w-56 space-y-2">
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-4/5" />
          <Skeleton className="h-4 w-2/3" />
        </div>
      </State>
      <State label="Avatar and name">
        <div className="flex items-center gap-3">
          <Skeleton className="size-10 rounded-full" />
          <div className="space-y-2">
            <Skeleton className="h-4 w-32" />
            <Skeleton className="h-3 w-24" />
          </div>
        </div>
      </State>
      <State label="Card">
        <Skeleton className="h-32 w-56 rounded-xl" />
      </State>
    </States>
  ),
};
