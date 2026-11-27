import type { Meta } from "@storybook/react-vite";
import { userEvent, within } from "storybook/test";

import {
  completedRun,
  failedRun,
  queuedRun,
  runningRun,
  stoppedRun,
} from "@/stories/grad-fixtures";
import { gradStoryHandlers } from "@/stories/grad-handlers";
import { settle } from "@/stories/grad-story";
import { Page, pageMeta, type PageStory } from "@/stories/page-story";

const meta = {
  ...pageMeta,
  title: "Pages/Training runs",
  parameters: { msw: gradStoryHandlers() },
  play: async ({ canvasElement }) => settle(canvasElement),
} satisfies Meta<typeof Page>;

export default meta;

const runPath = (id: string) => `/training/runs/${id}`;

export const Runs: PageStory = { args: { path: "/training/runs" } };

export const Empty: PageStory = {
  args: { path: "/training/runs" },
  parameters: { msw: gradStoryHandlers({ runs: [] }) },
};

export const Loading: PageStory = {
  args: { path: "/training/runs" },
  parameters: { msw: gradStoryHandlers({ loading: true }) },
  play: async ({ canvasElement }) => {
    await within(canvasElement).findByRole("heading", { level: 1 });
  },
};

export const LiveRun: PageStory = {
  args: { path: runPath(runningRun.id) },
  play: async ({ canvasElement }) => {
    await settle(canvasElement);
    await within(canvasElement).findByText("Compute reclaimed at step 860");
  },
};

export const CompletedRun: PageStory = {
  args: { path: runPath(completedRun.id) },
};

export const WaitingForCompute: PageStory = {
  args: { path: runPath(queuedRun.id) },
};

export const StoppedAtCostCap: PageStory = {
  args: { path: runPath(stoppedRun.id) },
  play: async ({ canvasElement }) => {
    await settle(canvasElement);
    await userEvent.click(
      await within(canvasElement).findByRole("button", { name: "Resume" }),
    );
    await within(canvasElement.ownerDocument.body).findByRole("heading", {
      name: "Resume with a higher cost cap",
    });
  },
};

export const FailedRun: PageStory = { args: { path: runPath(failedRun.id) } };

const openDeploy = async (canvasElement: HTMLElement) => {
  await settle(canvasElement);
  await userEvent.click(
    await within(canvasElement).findByRole("button", { name: "Deploy" }),
  );
  const body = within(canvasElement.ownerDocument.body);
  await userEvent.click(
    await body.findByRole("button", { name: "Publish version" }),
  );

  return body;
};

export const DeployNotAvailableYet: PageStory = {
  tags: ["request-failure"],
  args: { path: runPath(completedRun.id) },
  play: async ({ canvasElement }) => {
    const body = await openDeploy(canvasElement);
    await body.findByText("Deploy is not available yet");
  },
};

export const DeployPublished: PageStory = {
  args: { path: runPath(completedRun.id) },
  parameters: { msw: gradStoryHandlers({ deploy: "published" }) },
  play: async ({ canvasElement }) => {
    const body = await openDeploy(canvasElement);
    await body.findByText("Published");
  },
};

export const NewRun: PageStory = {
  args: { path: "/training/runs/new?dataset=support-traces" },
  play: async ({ canvasElement }) => {
    await settle(canvasElement);
    await userEvent.click(
      await within(canvasElement).findByRole("button", {
        name: "Estimate cost",
      }),
    );
    await within(canvasElement).findByText("$50.80");
  },
};

export const NewRunPlanRefused: PageStory = {
  tags: ["request-failure"],
  args: { path: "/training/runs/new?dataset=support-traces" },
  parameters: { msw: gradStoryHandlers({ planError: true }) },
  play: async ({ canvasElement }) => {
    await settle(canvasElement);
    await userEvent.click(
      await within(canvasElement).findByRole("button", {
        name: "Estimate cost",
      }),
    );
    await within(canvasElement).findByText(/needs about 96 GB/);
  },
};
