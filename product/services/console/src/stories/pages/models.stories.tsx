import type { Meta } from "@storybook/react-vite";

import { Page, pageMeta, type PageStory } from "@/stories/page-story";
import { newOrganizationHandlers } from "@/stories/handlers";

const meta = { ...pageMeta, title: "Pages/Models" } satisfies Meta<typeof Page>;

export default meta;

export const Default: PageStory = { args: { path: "/models" } };
export const Welcome: PageStory = {
  args: { path: "/models?welcome=true" },
  parameters: { msw: newOrganizationHandlers },
};
