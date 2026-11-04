import type { Meta } from "@storybook/react-vite";

import { Page, pageMeta, type PageStory } from "@/stories/page-story";

const meta = { ...pageMeta, title: "Pages/Logs" } satisfies Meta<typeof Page>;

export default meta;

export const Default: PageStory = { args: { path: "/logs" } };
export const Details: PageStory = {
  args: { path: "/logs" },
  parameters: { logDetail: true },
};
