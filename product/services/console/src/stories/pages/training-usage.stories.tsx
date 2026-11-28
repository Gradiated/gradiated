import type { Meta } from "@storybook/react-vite";
import { userEvent, within } from "storybook/test";

import { gradStoryHandlers } from "@/stories/grad-handlers";
import { settle } from "@/stories/grad-story";
import { Page, pageMeta, type PageStory } from "@/stories/page-story";

const meta = {
  ...pageMeta,
  title: "Pages/Training usage",
  parameters: { msw: gradStoryHandlers() },
  play: async ({ canvasElement }) => settle(canvasElement),
} satisfies Meta<typeof Page>;

export default meta;

export const ByDay: PageStory = { args: { path: "/training/usage" } };

export const ByModel: PageStory = {
  args: { path: "/training/usage" },
  play: async ({ canvasElement }) => {
    await settle(canvasElement);
    await userEvent.click(
      await within(canvasElement).findByRole(
        "combobox",
        { name: "Group usage" },
        { timeout: 10000 },
      ),
    );
    await userEvent.click(
      await within(canvasElement.ownerDocument.body).findByRole("option", {
        name: "By model",
      }),
    );
    await settle(canvasElement);
    await within(canvasElement).findByText("qwen3-1.7b");
  },
};
