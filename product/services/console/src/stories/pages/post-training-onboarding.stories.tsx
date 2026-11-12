import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, userEvent, waitFor, within } from "storybook/test";

import { Page } from "@/stories/page-story";
import {
  acmeInstallation,
  invitedSlack,
  manyRepositories,
  noRepositories,
  notStarted,
  onboardingHandlers,
  severalAccounts,
  signedNda,
  type OnboardingScenario,
} from "@/stories/onboarding-handlers";

const path = "/onboarding?journey=post-training";

type Step =
  "sendInvite" | "useEmail" | "requestNda" | "start" | "installGithub";

const meta = {
  title: "Pages/Post-training onboarding",
  component: Page,
  args: { path },
  render: (args, { id }) => <Page key={id} {...args} />,
  // Drafts persist per user and organization; start every story clean.
  beforeEach: () => {
    for (const key of Object.keys(localStorage))
      if (key.startsWith("gradiated-engineer-onboarding"))
        localStorage.removeItem(key);
  },
  play: async ({ canvasElement, parameters }) => {
    const canvas = within(canvasElement);
    const body = within(canvasElement.ownerDocument.body);
    await canvas.findByRole("heading", { level: 1 }, { timeout: 10000 });

    for (const step of (parameters.steps ?? []) as Step[]) {
      if (step === "installGithub") {
        // The story cannot follow the GitHub popup; it only opens it.
        window.open = () => null;
        await userEvent.click(
          await canvas.findByRole("button", { name: /Install GitHub app/ }),
        );
        await canvas.findByText("Waiting for GitHub…");
      }
      if (step === "sendInvite") {
        const send = await canvas.findByRole("button", { name: "Send invite" });
        await waitFor(() => expect(send).toBeEnabled());
        await userEvent.click(send);
      }
      if (step === "useEmail")
        await userEvent.click(
          await canvas.findByRole("checkbox", { name: /use email instead/ }),
        );
      if (step === "requestNda") {
        await userEvent.click(
          await canvas.findByRole("checkbox", {
            name: "We’d like a mutual NDA first",
          }),
        );
        await userEvent.type(
          await canvas.findByRole("textbox", { name: "Signer’s title" }),
          "CTO",
        );
        await userEvent.type(
          await canvas.findByRole("textbox", { name: "Company address" }),
          "500 Market Street, San Francisco, CA 94105",
        );
      }
      if (step === "start") {
        const start = await canvas.findByRole("button", {
          name: /start project/i,
        });
        await waitFor(() => expect(start).toBeEnabled(), { timeout: 10000 });
        await userEvent.click(start);
      }
    }

    if (parameters.expectText)
      await body.findByText(parameters.expectText, {}, { timeout: 10000 });
  },
} satisfies Meta<typeof Page>;

export default meta;

type Story = StoryObj<typeof meta>;

const scenario = (options: OnboardingScenario) => ({
  msw: onboardingHandlers(options),
});

export const FirstVisit: Story = {
  parameters: scenario({ unlinked: true }),
};

export const WaitingForGithub: Story = {
  parameters: {
    ...scenario({ unlinked: true }),
    steps: ["installGithub"],
  },
};

export const GithubInstalled: Story = {
  parameters: {
    ...scenario({ installations: [acmeInstallation()] }),
    expectText: "acme/trainer",
  },
};

export const ManyRepositories: Story = {
  parameters: {
    ...scenario({ installations: [manyRepositories] }),
    expectText: "and 42 more",
  },
};

export const NoRepositoriesSelected: Story = {
  parameters: {
    ...scenario({ installations: [noRepositories] }),
    expectText: /no repositories selected/,
  },
};

export const SeveralGithubAccounts: Story = {
  parameters: {
    ...scenario({ installations: severalAccounts }),
    expectText: "Show 2 more",
  },
};

export const SlackInviteSent: Story = {
  parameters: {
    ...scenario({ installations: [acmeInstallation()] }),
    steps: ["sendInvite"],
    expectText: /Resend in \d+s/,
  },
};

export const SlackChannelTaken: Story = {
  parameters: {
    ...scenario({
      installations: [acmeInstallation()],
      slackInvite: "channel_taken",
    }),
    steps: ["sendInvite"],
    expectText: "That channel name is already in use.",
  },
};

export const EmailInsteadOfSlack: Story = {
  parameters: {
    ...scenario({ installations: [acmeInstallation()] }),
    steps: ["useEmail"],
    expectText: /If you can use Slack later/,
  },
};

export const ReadyToStart: Story = {
  parameters: {
    ...scenario({
      onboarding: { ...notStarted, slack: invitedSlack },
      installations: [acmeInstallation()],
    }),
    expectText: "You can change any of this later.",
  },
};

export const NdaRequested: Story = {
  parameters: {
    ...scenario({
      onboarding: { ...notStarted, slack: invitedSlack },
      installations: [acmeInstallation()],
    }),
    steps: ["requestNda"],
    expectText: "Sign your mutual NDA",
  },
};

export const SigningNda: Story = {
  parameters: {
    ...scenario({
      onboarding: { ...notStarted, slack: invitedSlack },
      installations: [acmeInstallation()],
    }),
    steps: ["requestNda", "start"],
    expectText: /Preparing|Review/,
  },
};

export const NdaSigned: Story = {
  parameters: {
    ...scenario({
      onboarding: { ...notStarted, slack: invitedSlack, nda: signedNda },
      installations: [acmeInstallation()],
    }),
    expectText: /Signed with PostHog Inc\./,
  },
};

export const Starting: Story = {
  parameters: {
    ...scenario({
      onboarding: { ...notStarted, slack: invitedSlack },
      installations: [acmeInstallation()],
      submission: "slow",
    }),
    steps: ["start"],
    expectText: "Starting project…",
  },
};

export const StartFailed: Story = {
  parameters: {
    ...scenario({
      onboarding: { ...notStarted, slack: invitedSlack },
      installations: [acmeInstallation()],
      submission: "github_repositories_required",
    }),
    steps: ["start"],
    expectText: "Go to repository access",
  },
};

export const ProjectStarted: Story = {
  parameters: {
    ...scenario({
      onboarding: { ...notStarted, slack: invitedSlack },
      installations: [acmeInstallation()],
    }),
    steps: ["start"],
    expectText: "You’re all set.",
  },
};

export const AlreadyStarted: Story = {
  parameters: {
    ...scenario({
      onboarding: {
        ...notStarted,
        slack: invitedSlack,
        contact_channel: "slack",
        github_installations: [
          { id: 4201, account: "acme", repository_selection: "selected" },
        ],
        submitted_at: "2026-11-12T10:30:00.000Z",
      },
      installations: [acmeInstallation()],
    }),
    expectText: "Your project is underway.",
  },
};

export const Mobile: Story = {
  parameters: {
    ...scenario({ installations: [acmeInstallation()] }),
  },
  globals: { viewport: { value: "mobile2", isRotated: false } },
};
