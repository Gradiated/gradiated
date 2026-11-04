import type { Meta } from "@storybook/react-vite";

import { Page, pageMeta, type PageStory } from "@/stories/page-story";

const meta = { ...pageMeta, title: "Pages/General" } satisfies Meta<
  typeof Page
>;

export default meta;

export const CreateWorkspace: PageStory = {
  args: { path: "/api-keys" },
  parameters: { createScope: "workspace" },
};
export const CreateOrganization: PageStory = {
  args: { path: "/api-keys" },
  parameters: { createScope: "organization" },
};
