import type { Meta } from "@storybook/react-vite";

import { Page, pageMeta, type PageStory } from "@/stories/page-story";

const meta = { ...pageMeta, title: "Pages/API keys" } satisfies Meta<
  typeof Page
>;

export default meta;

export const Default: PageStory = { args: { path: "/api-keys" } };
export const CreateApiKey: PageStory = {
  args: { path: "/api-keys" },
  parameters: { createApiKey: true },
};
