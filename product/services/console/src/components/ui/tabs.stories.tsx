import type { Meta, StoryObj } from "@storybook/react-vite";
import { useState } from "react";

import { State, States } from "@/stories/states";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "./tabs";

const meta = { title: "Components/Tabs" } satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

const TaskTabs = ({ initial }: { initial: string }) => {
  const [tab, setTab] = useState(initial);

  return (
    <Tabs value={tab} onValueChange={setTab}>
      <TabsList>
        <TabsTrigger value="model">Model</TabsTrigger>
        <TabsTrigger value="runs">Training runs</TabsTrigger>
        <TabsTrigger value="data">Data</TabsTrigger>
      </TabsList>
      <TabsContent value="model" className="pt-3 text-sm text-muted-foreground">
        Production version: support-triage-v2
      </TabsContent>
      <TabsContent value="runs" className="pt-3 text-sm text-muted-foreground">
        No training runs yet.
      </TabsContent>
      <TabsContent value="data" className="pt-3 text-sm text-muted-foreground">
        1,204 captured traces.
      </TabsContent>
    </Tabs>
  );
};

export const States_: Story = {
  name: "States",
  render: () => (
    <States className="grid-cols-[repeat(auto-fill,minmax(22rem,1fr))]">
      <State label="First tab selected">
        <TaskTabs initial="model" />
      </State>
      <State label="Middle tab selected">
        <TaskTabs initial="runs" />
      </State>
      <State label="Last tab selected">
        <TaskTabs initial="data" />
      </State>
    </States>
  ),
};
