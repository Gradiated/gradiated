import type { Meta } from "@storybook/react-vite";

import { Page, pageMeta, type PageStory } from "@/stories/page-story";

const meta = { ...pageMeta, title: "Pages/Usage" } satisfies Meta<typeof Page>;

export default meta;

export const Usage: PageStory = { args: { path: "/usage" } };
