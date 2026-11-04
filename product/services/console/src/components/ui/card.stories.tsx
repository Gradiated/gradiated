import type { Meta, StoryObj } from "@storybook/react-vite";

import { State, States } from "@/stories/states";
import { Button } from "./button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "./card";

const meta = { title: "Components/Card" } satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

export const Variants: Story = {
  render: () => (
    <States className="grid-cols-[repeat(auto-fill,minmax(20rem,1fr))]">
      <State label="Header, content and footer">
        <Card className="w-full">
          <CardHeader>
            <CardTitle>Balance</CardTitle>
            <CardDescription>
              Prepaid credit for this organization.
            </CardDescription>
          </CardHeader>
          <CardContent className="text-3xl font-semibold">$42.18</CardContent>
          <CardFooter className="gap-2">
            <Button>Top up</Button>
            <Button variant="outline">Auto top-up</Button>
          </CardFooter>
        </Card>
      </State>
      <State label="Header only">
        <Card className="w-full">
          <CardHeader>
            <CardTitle>No models yet</CardTitle>
            <CardDescription>
              Upload a LoRA adapter to create your first model.
            </CardDescription>
          </CardHeader>
        </Card>
      </State>
      <State label="Content only">
        <Card className="w-full">
          <CardContent className="pt-6 text-sm text-muted-foreground">
            Requests in the last 24 hours: 12,408
          </CardContent>
        </Card>
      </State>
    </States>
  ),
};
