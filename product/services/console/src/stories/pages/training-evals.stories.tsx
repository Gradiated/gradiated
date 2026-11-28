import type { Meta } from "@storybook/react-vite";
import { within } from "storybook/test";

import { evals } from "@/stories/grad-fixtures";
import { gradStoryHandlers } from "@/stories/grad-handlers";
import { settle } from "@/stories/grad-story";
import { Page, pageMeta, type PageStory } from "@/stories/page-story";

const meta = {
  ...pageMeta,
  title: "Pages/Training evals",
  parameters: { msw: gradStoryHandlers() },
  play: async ({ canvasElement }) => settle(canvasElement),
} satisfies Meta<typeof Page>;

export default meta;

export const Evals: PageStory = { args: { path: "/training/evals" } };

export const CompletedEval: PageStory = {
  args: { path: `/training/evals/${evals[0]?.id}` },
  play: async ({ canvasElement }) => {
    await settle(canvasElement);
    await within(canvasElement).findByText("task_0042");
  },
};

export const RunningEval: PageStory = {
  args: { path: `/training/evals/${evals[1]?.id}` },
};
