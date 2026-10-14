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
import {
  acmeOwner,
  handlersFor,
  newOrganizationHandlers,
  onboardingCompanyUser,
  onboardingPersonalUser,
} from "./handlers";

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

    if (parameters.settingsTab) {
      await userEvent.click(
        await canvas.findByRole("tab", { name: parameters.settingsTab }),
      );
      const input = await canvas.findByRole("textbox", {
        name: `${parameters.settingsTab} name`,
      });
      await expect(input).toHaveAttribute("data-1p-ignore", "true");
      await expect(input).toHaveAttribute("autocomplete", "off");
    }

    if (parameters.createScope) {
      const workspace = parameters.createScope === "workspace";
      await userEvent.click(
        await canvas.findByRole("button", {
          name: workspace ? "Workspace menu" : "Account menu",
        }),
      );
      if (!workspace)
        await userEvent.hover(
          await body.findByRole("menuitem", { name: "Change organization" }),
        );
      await userEvent.click(
        await body.findByRole("menuitem", {
          name: workspace ? "Add workspace" : "Add organization",
        }),
      );
      const input = await body.findByRole("textbox", {
        name: workspace ? "Workspace name" : "Organization name",
      });
      await expect(input).toHaveAttribute("data-1p-ignore", "true");
      await expect(input).toHaveAttribute("name", "scopeLabel");
      await userEvent.type(input, workspace ? "Production" : "Acme Inc");
    }

    if (parameters.createApiKey) {
      const create = await canvas.findByRole("button", {
        name: "Create API key",
      });
      await waitFor(() => expect(create).toBeEnabled());
      await userEvent.click(create);
      const name = await body.findByRole("textbox", { name: "Name" });
      await expect(name).toHaveAttribute("data-1p-ignore", "true");
      await userEvent.type(name, "Production");
    }

    if (parameters.logDetail) {
      await userEvent.click(
        await canvas.findByRole("button", { name: /^storyboo/ }),
      );
      await body.findByRole("heading", { name: "storybook-generation" });
      const model = body.getAllByText("GLM-5.3 Flash", { exact: true }).at(-1);
      await waitFor(() => {
        const icon = model?.parentElement?.querySelector("img");
        expect(icon?.complete && icon.naturalWidth > 0).toBe(true);
      });
    }

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
      await body.findByText(/22 output tokens · 0.28s · \$0.000300/);
      await expect(body.queryByText(/^Group:/)).toBeNull();
      await expect(body.queryByText(/answer first\)/)).toBeNull();
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

    if (parameters.modelSelect) {
      await userEvent.click(
        await canvas.findByRole("combobox", { name: parameters.modelSelect }),
      );
      if (parameters.modelSearch) {
        await userEvent.type(
          await body.findByRole("combobox", {
            name: `Search ${parameters.modelSelect.toLowerCase()}`,
          }),
          parameters.modelSearch,
        );
        await waitFor(() =>
          expect(
            body.queryByRole("option", { name: "GPT-6.1 Sol" }),
          ).toBeNull(),
        );
      }
      const option = await body.findByRole("option", {
        name: parameters.modelSearch ? "GPT-4.1 Mini" : "GPT-6.1 Sol",
      });
      await waitFor(() => {
        const icon = option.querySelector("img");
        expect(icon?.complete && icon.naturalWidth > 0).toBe(true);
      });
    }

    canvasElement.dataset.storyPlayed = "true";
  },
} satisfies Meta<typeof Page>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Login: Story = { args: { path: "/login" } };
export const ApiKeys: Story = { args: { path: "/api-keys" } };
export const CreateApiKey: Story = {
  args: { path: "/api-keys" },
  parameters: { createApiKey: true },
};
export const Models: Story = { args: { path: "/models" } };
export const Usage: Story = { args: { path: "/usage" } };
export const Logs: Story = { args: { path: "/logs" } };
export const LogDetails: Story = {
  args: { path: "/logs" },
  parameters: { logDetail: true },
};
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

export const TaskJudgeSelector: Story = {
  args: { path: "/tasks/support-assistant" },
  parameters: { taskTab: "Settings", modelSelect: "Judge model" },
};

export const TaskTrace: Story = {
  args: { path: "/tasks/support-assistant" },
  parameters: { taskTab: "Data", taskDetail: "trace" },
};
export const TaskTestResults: Story = {
  args: { path: "/tasks/support-assistant" },
  parameters: { taskTab: "Model", taskDetail: "results" },
};

export const SettingsWorkspace: Story = {
  args: { path: "/settings" },
  parameters: { settingsTab: "Workspace" },
};
export const SettingsOrganization: Story = {
  args: { path: "/settings" },
  parameters: { settingsTab: "Organization", msw: handlersFor(acmeOwner) },
};
export const Onboarding: Story = {
  args: { path: "/onboarding" },
  parameters: { msw: handlersFor(onboardingCompanyUser) },
};
export const OnboardingPersonalEmail: Story = {
  args: { path: "/onboarding" },
  parameters: { msw: handlersFor(onboardingPersonalUser) },
};
export const ModelsWelcome: Story = {
  args: { path: "/models?welcome=true" },
  parameters: { msw: newOrganizationHandlers },
};
export const CreateWorkspace: Story = {
  args: { path: "/api-keys" },
  parameters: { createScope: "workspace" },
};
export const CreateOrganization: Story = {
  args: { path: "/api-keys" },
  parameters: { createScope: "organization" },
};
export const TaskComparisonSelector: Story = {
  args: { path: "/tasks/support-assistant" },
  parameters: {
    taskTab: "Settings",
    modelSelect: "Comparison model",
    modelSearch: "4.1",
  },
};
