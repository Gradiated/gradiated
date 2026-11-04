import NiceModal from "@ebay/nice-modal-react";
import { QueryClientProvider, useIsFetching } from "@tanstack/react-query";
import { createMemoryHistory, RouterProvider } from "@tanstack/react-router";
import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, userEvent, within, waitFor } from "storybook/test";
import { useState } from "react";

import { Toaster } from "@/components/ui/sonner";
import { createStoryQueryClient } from "@/stories/query-client";
import { createConsoleRouter } from "@/router";
import { usePlaygroundStore } from "@/store/playground";

const Ready = () => {
  const fetching = useIsFetching();

  return <span hidden data-story-ready={fetching === 0} />;
};

export const Page = ({ path }: { path: string }) => {
  const [queryClient] = useState(() => {
    // The playground conversation persists to localStorage across stories.
    usePlaygroundStore.getState().reset();
    return createStoryQueryClient();
  });
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

export const pageMeta = {
  component: Page,
  // Key by story so switching stories never reuses another story's cache or state.
  render: (args, { id }) => <Page key={id} {...args} />,
  play: async ({ canvasElement, parameters }) => {
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

    if (parameters.nameField) {
      const input = await canvas.findByRole("textbox", {
        name: parameters.nameField,
      });
      await expect(input).toHaveAttribute("data-1p-ignore", "true");
      await expect(input).toHaveAttribute("autocomplete", "off");
    }

    if (parameters.members) {
      await canvas.findByText("morgan@acme.com", {}, { timeout: 10000 });
    }

    if (parameters.invite) {
      await userEvent.click(
        await canvas.findByRole("button", { name: /Invite/ }),
      );
      await userEvent.type(
        await body.findByRole("textbox", { name: "Email addresses" }),
        "morgan@acme.com, casey@acme.com",
      );
      await body.findByRole("button", { name: "Send 2 invitations" });
    }

    if (parameters.memberActions) {
      await userEvent.click(
        await canvas.findByRole("button", {
          name: `Actions for ${parameters.memberActions}`,
        }),
      );
      await body.findByRole("menuitem", { name: /Remove from/ });
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

    if (
      parameters.playground === "conversation" ||
      parameters.playground === "unavailable"
    ) {
      const message = await canvas.findByRole("textbox", { name: "Message" });
      await waitFor(() => expect(message).toBeEnabled());
      await userEvent.type(message, "Write a haiku about fast inference.");
      await userEvent.click(
        canvas.getByRole("button", { name: "Send message" }),
      );
    }

    if (parameters.playground === "conversation") {
      await canvas.findByText(/to first token/, {}, { timeout: 10000 });
      await canvas.findByText(/before the thought ends/);
    }

    if (parameters.playground === "unavailable") {
      await canvas.findByText(
        "The playground is unavailable in an archived workspace or a suspended organization.",
      );
    }

    if (parameters.playground === "models") {
      const model = await canvas.findByRole("combobox", { name: "Model" });
      await waitFor(() => expect(model).toBeEnabled());
      await userEvent.click(model);
      await body.findByRole("group", { name: "Your models" });
      await body.findByRole("option", { name: "support-assistant" });
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
        expect(body.queryAllByRole("alert")).toHaveLength(
          parameters.playground === "unavailable" ? 1 : 0,
        );
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
  },
} satisfies Meta<typeof Page>;

export type PageStory = StoryObj<typeof pageMeta>;
