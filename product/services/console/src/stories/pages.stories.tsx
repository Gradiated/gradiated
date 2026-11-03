import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, userEvent, within, waitFor } from "storybook/test";

import { StoryPage as Page } from "./story-page";
import {
  acmeAdmin,
  acmeMember,
  billingHandlers,
  billingLoadingHandlers,
  handlersFor,
  invitationHandlers,
  invitationPreview,
  invitee,
  otherAccount,
  newOrganizationHandlers,
  onboardingCompanyUser,
  onboardingPersonalUser,
  playgroundHandlers,
  playgroundUnavailableHandlers,
} from "./handlers";

const meta = {
  title: "Pages",
  component: Page,
  render: (args) => <Page key={args.path} {...args} />,
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

export default meta;
type Story = StoryObj<typeof meta>;

export const Login: Story = { args: { path: "/login" } };
export const ApiKeys: Story = { args: { path: "/api-keys" } };
export const CreateApiKey: Story = {
  args: { path: "/api-keys" },
  parameters: { createApiKey: true },
};
export const Models: Story = { args: { path: "/models" } };
export const Playground: Story = {
  args: { path: "/playground" },
  parameters: { msw: playgroundHandlers },
};
export const PlaygroundConversation: Story = {
  args: { path: "/playground" },
  parameters: { playground: "conversation", msw: playgroundHandlers },
};
export const PlaygroundUnavailable: Story = {
  args: { path: "/playground" },
  tags: ["request-failure"],
  parameters: { playground: "unavailable", msw: playgroundUnavailableHandlers },
};
export const PlaygroundModels: Story = {
  args: { path: "/playground" },
  parameters: { playground: "models", msw: playgroundHandlers },
};
export const Usage: Story = { args: { path: "/usage" } };
export const Logs: Story = { args: { path: "/logs" } };
export const LogDetails: Story = {
  args: { path: "/logs" },
  parameters: { logDetail: true },
};
export const Billing: Story = { args: { path: "/billing" } };
export const BillingLoading: Story = {
  args: { path: "/billing" },
  parameters: { msw: billingLoadingHandlers },
};
export const BillingWithoutCard: Story = {
  args: { path: "/billing" },
  parameters: {
    msw: billingHandlers({
      payment_method: null,
      auto_top_up: {
        enabled: false,
        threshold: null,
        amount: null,
        failure: null,
      },
    }),
  },
};
export const BillingAutoTopUpOff: Story = {
  args: { path: "/billing" },
  parameters: {
    msw: billingHandlers({
      auto_top_up: {
        enabled: false,
        threshold: null,
        amount: null,
        failure: null,
      },
    }),
  },
};
export const BillingMastercard: Story = {
  args: { path: "/billing" },
  parameters: {
    msw: billingHandlers({
      payment_method: {
        brand: "mastercard",
        last4: "4444",
        exp_month: 3,
        exp_year: 2027,
      },
    }),
  },
};
export const BillingAutoTopUpFailed: Story = {
  args: { path: "/billing" },
  parameters: {
    msw: billingHandlers({
      auto_top_up: {
        enabled: false,
        threshold: "10000000000",
        amount: "50000000000",
        failure: "Your card was declined.",
      },
    }),
  },
};
export const BillingAsMember: Story = {
  args: { path: "/billing" },
  parameters: { msw: handlersFor(acmeMember) },
};
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
  args: { path: "/settings/workspace" },
  parameters: { nameField: "Workspace name" },
};
export const SettingsOrganization: Story = {
  args: { path: "/settings/organization" },
  parameters: { nameField: "Organization name", msw: handlersFor(acmeAdmin) },
};
export const SettingsMembers: Story = {
  args: { path: "/settings/members" },
  parameters: { members: true, msw: handlersFor(acmeAdmin) },
};
export const SettingsMembersMobile: Story = {
  args: { path: "/settings/members" },
  parameters: { members: true, msw: handlersFor(acmeAdmin) },
  tags: ["mobile"],
};
export const SettingsMembersAsMember: Story = {
  args: { path: "/settings/members" },
  parameters: { members: true, msw: handlersFor(acmeMember) },
};
export const SettingsMemberActions: Story = {
  args: { path: "/settings/members" },
  parameters: {
    members: true,
    memberActions: "sam@acme.com",
    msw: handlersFor(acmeAdmin),
  },
};
export const InviteMembers: Story = {
  args: { path: "/settings/members" },
  parameters: { members: true, invite: true, msw: handlersFor(acmeAdmin) },
};
export const SettingsOrganizationMobile: Story = {
  args: { path: "/settings/organization" },
  parameters: { nameField: "Organization name", msw: handlersFor(acmeAdmin) },
  tags: ["mobile"],
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

const invitationStory = (
  preview: Parameters<typeof invitationHandlers>[0],
  currentUser: Parameters<typeof invitationHandlers>[1],
): Story => ({
  args: { path: `/invitations/accept?token=${"a".repeat(43)}` },
  parameters: { msw: invitationHandlers(preview, currentUser) },
});

export const InvitationAccept = invitationStory(invitationPreview, invitee);
export const InvitationSignedOut = invitationStory(invitationPreview, null);
export const InvitationWrongAccount = invitationStory(
  invitationPreview,
  otherAccount,
);
export const InvitationExpired = invitationStory(
  { ...invitationPreview, status: "expired" },
  invitee,
);
export const InvitationInvalid = invitationStory({ status: "invalid" }, null);
export const InvitationAlreadyMember = invitationStory(
  { ...invitationPreview, email: "priya@acme.com" },
  acmeMember,
);
export const InvitationError: Story = {
  ...invitationStory("error", invitee),
  tags: ["request-failure"],
};
