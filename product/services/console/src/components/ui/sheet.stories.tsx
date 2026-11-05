import type { Meta, StoryObj } from "@storybook/react-vite";

import { Button } from "./button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "./sheet";

const meta = { title: "Components/Sheet" } satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

const sheet = (side: "top" | "right" | "bottom" | "left"): Story => ({
  render: () => (
    <Sheet open>
      <SheetContent side={side}>
        <SheetHeader>
          <SheetTitle>Generation details</SheetTitle>
          <SheetDescription>gen_01a1a79d · z-ai/glm-5.3-flash</SheetDescription>
        </SheetHeader>
        <dl className="mt-6 grid grid-cols-2 gap-y-2 text-sm">
          <dt className="text-muted-foreground">Input tokens</dt>
          <dd>1,204</dd>
          <dt className="text-muted-foreground">Output tokens</dt>
          <dd>312</dd>
          <dt className="text-muted-foreground">Cost</dt>
          <dd>$0.0004</dd>
        </dl>
        <SheetFooter className="mt-6">
          <Button variant="outline">Close</Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  ),
});

export const Right = sheet("right");
export const Left = sheet("left");
export const Bottom = sheet("bottom");
export const Top = sheet("top");
