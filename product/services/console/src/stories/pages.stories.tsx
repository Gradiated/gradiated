import NiceModal from "@ebay/nice-modal-react";
import {
  QueryClient,
  QueryClientProvider,
  useIsFetching,
} from "@tanstack/react-query";
import { createMemoryHistory, RouterProvider } from "@tanstack/react-router";
import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, userEvent, within, waitFor } from "storybook/test";
import { useState } from "react";

import { Toaster } from "@/components/ui/sonner";
import { createConsoleRouter } from "@/router";

const Ready = () => {
  const fetching = useIsFetching();

  return <span hidden data-story-ready={fetching === 0} />;
};

const Page = ({ path }: { path: string }) => {
  const [queryClient] = useState(
    () => new QueryClient({ defaultOptions: { queries: { retry: false } } }),
  );
  const [router] = useState(() =>
    createConsoleRouter(createMemoryHistory({ initialEntries: [path] })),
  );

  return (
    <QueryClientProvider client={queryClient}>
      <NiceModal.Provider>
        <RouterProvider router={router} />
        <Toaster />
        <Ready />
      </NiceModal.Provider>
    </QueryClientProvider>
  );
};

const meta = {
  title: "Pages",
  component: Page,
  render: (args) => <Page key={args.path} {...args} />,
  play: async ({ canvasElement, parameters }) => {
    delete canvasElement.dataset.storyPlayed;
    const canvas = within(canvasElement);
    await canvas.findByRole("heading", { level: 1 }, { timeout: 10000 });

    if (parameters.taskTab) {
      const tab = await canvas.findByRole(
        "tab",
        { name: parameters.taskTab },
        { timeout: 10000 },
      );
      await userEvent.click(tab);
      await expect(tab).toHaveAttribute("aria-selected", "true");
    }

    const body = within(canvasElement.ownerDocument.body);

    if (parameters.taskDetail === "trace") {
      await userEvent.click(
        await canvas.findByRole("button", { name: "storybook-trace" }),
      );
      await body.findByRole("heading", { name: /request/i });
      await body.findByText(/How can I reset my password/);
      await body.findByText(/Select Forgot password/);
    }

    if (parameters.taskDetail === "results") {
      await userEvent.click(
        await canvas.findByRole("button", { name: "View test results →" }),
      );
      await body.findByRole("heading", { name: "Test results" });
      await body.findByRole("heading", { name: "Example 1" });
      await body.findByText("Better", { exact: true });
    }

    await waitFor(
      () => {
        expect(
          canvasElement.querySelector("[data-story-ready=true]"),
        ).not.toBeNull();
        expect(
          canvasElement.ownerDocument.body.querySelector(".animate-pulse"),
        ).toBeNull();
        expect(body.queryAllByRole("alert")).toHaveLength(0);
      },
      { timeout: 10000 },
    );
    canvasElement.dataset.storyPlayed = "true";
  },
} satisfies Meta<typeof Page>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Login: Story = { args: { path: "/login" } };
export const ApiKeys: Story = { args: { path: "/api-keys" } };
export const Models: Story = { args: { path: "/models" } };
export const Usage: Story = { args: { path: "/usage" } };
export const Logs: Story = { args: { path: "/logs" } };
export const Billing: Story = { args: { path: "/billing" } };
export const Training: Story = { args: { path: "/tasks" } };
export const TaskModel: Story = {
  args: { path: "/tasks/support-assistant" },
  parameters: { taskTab: "Model" },
};
export const TaskRuns: Story = {
  args: { path: "/tasks/support-assistant" },
  parameters: { taskTab: "Training runs" },
};
export const TaskData: Story = {
  args: { path: "/tasks/support-assistant" },
  parameters: { taskTab: "Data" },
};
export const TaskSettings: Story = {
  args: { path: "/tasks/support-assistant" },
  parameters: { taskTab: "Settings" },
};

export const TaskTrace: Story = {
  args: { path: "/tasks/support-assistant" },
  parameters: { taskTab: "Data", taskDetail: "trace" },
};
export const TaskTestResults: Story = {
  args: { path: "/tasks/support-assistant" },
  parameters: { taskTab: "Model", taskDetail: "results" },
};
